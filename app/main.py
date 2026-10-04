"""Rutas HTTP y arranque.

Arrancar con UN solo proceso (uvicorn sin --workers): la base de datos es
SQLite y el bucle de tareas vive dentro del proceso.
"""
import asyncio
import json
import logging
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from app import onboarding, service, telephony
from app.agent import Agent
from app.config import settings
from app.db import Database, now
from app.notify import notify_owner
from app.phone import normalize
from app.whatsapp import parse_webhook, verify_signature, whatsapp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx registra cada URL a nivel INFO; no aporta y llena el log.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("app")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")


def seed_clinics(db: Database, path: str) -> int:
    """Carga las clínicas del fichero SOLO si no existen: una vez en la base de
    datos, se editan allí (Supabase o /admin) y el fichero no las pisa."""
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        clinics = json.load(f)
    for c in clinics:
        db.upsert_clinic(c, overwrite=False)
    return len(clinics)


async def worker_loop(app: FastAPI) -> None:
    last_maintenance = 0.0
    while True:
        try:
            await service.tick(app.state.db, app.state.agent)
            if time.time() - last_maintenance > 3600:
                service.maintenance(app.state.db)
                last_maintenance = time.time()
        except Exception:
            log.exception("Error en el bucle de tareas")
        await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = Database(settings.database_url or settings.database_path, settings.db_schema)
    app.state.agent = Agent(app.state.db)
    seed_clinics(app.state.db, settings.clinics_file)
    log.info("Base de datos: %s. Clínicas: %s. WhatsApp %s. LLM %s.",
             "Supabase/Postgres" if app.state.db.pg else "SQLite", len(app.state.db.list_clinics()),
             "SIMULADO" if whatsapp.dry_run else "real",
             settings.gemini_model if settings.gemini_api_key else "sin key")
    task = None
    if os.getenv("DISABLE_WORKER") != "1":
        task = asyncio.create_task(worker_loop(app))
    yield
    if task:
        task.cancel()


app = FastAPI(title="RecuperaPacientes", lifespan=lifespan, docs_url=None, redoc_url=None)


def _db(request: Request) -> Database:
    return request.app.state.db


# ------------------------------------------------------------------ páginas
@app.get("/", include_in_schema=False)
def landing():
    return FileResponse(os.path.join(WEB, "index.html"))


@app.get("/panel", include_in_schema=False)
def panel_page():
    return FileResponse(os.path.join(WEB, "panel.html"))


@app.get("/alta", include_in_schema=False)
def application_page():
    return FileResponse(os.path.join(WEB, "alta.html"))


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(os.path.join(WEB, "admin.html"))


@app.get("/privacidad", include_in_schema=False)
def privacy_page():
    return FileResponse(os.path.join(WEB, "privacidad.html"))


@app.get("/salud")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- WhatsApp
@app.get("/webhooks/whatsapp")
def wa_verify(request: Request):
    q = request.query_params
    if (settings.wa_verify_token and q.get("hub.mode") == "subscribe"
            and secrets.compare_digest(q.get("hub.verify_token", ""), settings.wa_verify_token)):
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403)


@app.post("/webhooks/whatsapp")
async def wa_webhook(request: Request, background: BackgroundTasks):
    raw = await request.body()
    if not verify_signature(raw, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(401, "firma no válida")
    events = parse_webhook(json.loads(raw or b"{}"))
    # Se responde 200 ya; Meta reintenta si tardamos y eso duplicaría mensajes.
    for ev in events:
        background.add_task(service.handle_inbound, _db(request), request.app.state.agent, ev)
    return {"ok": True}


# ---------------------------------------------------------------- llamadas
class CallEvent(BaseModel):
    to: Optional[str] = None
    clinica_id: Optional[str] = None
    from_: str = Field(..., alias="from")
    id: str
    estado: str = "perdida"


@app.post("/webhooks/llamada")
def generic_call(request: Request, ev: CallEvent, x_webhook_token: str = Header("")):
    if not settings.call_webhook_token:
        raise HTTPException(503, "Define CALL_WEBHOOK_TOKEN para activar esta ruta")
    if not secrets.compare_digest(x_webhook_token, settings.call_webhook_token):
        raise HTTPException(401)
    db = _db(request)
    clinic = db.get_clinic(ev.clinica_id) if ev.clinica_id else db.clinic_by_called_number(normalize(ev.to))
    if not clinic:
        raise HTTPException(404, "No hay clínica para ese número")
    if ev.estado == "atendida":
        return {"canceladas": service.register_answered_call(db, clinic, ev.from_)}
    return {"resultado": service.register_missed_call(db, clinic, ev.from_, ev.id)}


async def _twilio_params(request: Request) -> Dict[str, str]:
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    url = settings.public_base_url + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    if not telephony.twilio_signature_ok(url, params, request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(401, "firma de Twilio no válida")
    return params


def _xml(body: str) -> Response:
    return Response(body, media_type="application/xml")


@app.post("/webhooks/twilio/voz")
async def twilio_voice(request: Request):
    p = await _twilio_params(request)
    clinic = _db(request).clinic_by_called_number(normalize(p.get("To")))
    if not clinic or not clinic.get("telefono_recepcion"):
        return _xml(telephony.twiml_say_and_hangup("Este número no está disponible."))
    return _xml(telephony.twiml_dial(clinic["telefono_recepcion"],
                                     settings.public_base_url + "/webhooks/twilio/fin",
                                     int(clinic.get("segundos_espera", 20))))


@app.post("/webhooks/twilio/fin")
async def twilio_dial_end(request: Request):
    p = await _twilio_params(request)
    db = _db(request)
    clinic = db.clinic_by_called_number(normalize(p.get("To")))
    if not clinic:
        return _xml(telephony.twiml("<Hangup/>"))
    if p.get("DialCallStatus") in telephony.DIAL_MISSED:
        service.register_missed_call(db, clinic, p.get("From", ""), p.get("CallSid", ""))
        return _xml(telephony.twiml_say_and_hangup(clinic.get("mensaje_voz", telephony.DEFAULT_MISSED_SAY)))
    service.register_answered_call(db, clinic, p.get("From", ""))
    return _xml(telephony.twiml("<Hangup/>"))


# ------------------------------------------------------------------- leads
_hits: Dict[str, List[float]] = {}


def _client_ip(request: Request) -> str:
    if settings.trust_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            # El último salto lo añade nuestro proxy; los anteriores los
            # puede inventar el cliente.
            return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "?"


def _rate_ok(ip: str, limit: int = 5, window: int = 600) -> bool:
    t = time.time()
    hits = [h for h in _hits.get(ip, []) if t - h < window]
    if len(_hits) > 10000:
        _hits.clear()
    _hits[ip] = hits + [t]
    return len(hits) < limit


class LeadIn(BaseModel):
    clinica: str = Field(..., min_length=2, max_length=160)
    nombre: Optional[str] = Field(None, max_length=120)
    telefono: str = Field(..., min_length=6, max_length=30)
    email: Optional[str] = Field(None, max_length=160)
    mensaje: Optional[str] = Field(None, max_length=1000)
    web: Optional[str] = Field(None, max_length=200)  # trampa para bots
    acepta: bool = False


@app.post("/api/leads")
async def create_lead(lead: LeadIn, request: Request):
    if lead.web:
        return {"ok": True}
    if not _rate_ok(_client_ip(request)):
        raise HTTPException(429, "Demasiados envíos. Prueba en unos minutos.")
    if not lead.acepta:
        raise HTTPException(400, "Necesitamos tu consentimiento para contactarte.")
    phone = normalize(lead.telefono)
    if len(re.sub(r"\D", "", phone)) < 9:
        raise HTTPException(400, "Revisa el teléfono.")
    if lead.email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", lead.email):
        raise HTTPException(400, "Revisa el email.")
    db = _db(request)
    if not db.recent_lead(phone, now() - 86400):
        db.add_lead(lead.clinica.strip(), lead.nombre, phone, lead.email, lead.mensaje)
        await notify_owner(f"🆕 Nuevo interesado\nClínica: {lead.clinica}\nContacto: {lead.nombre or '-'}\n"
                           f"Teléfono: {phone}\nEmail: {lead.email or '-'}\n{lead.mensaje or ''}")
    return {"ok": True}


# ------------------------------------------------------------ ficha de alta
@app.post("/api/altas")
async def create_application(body: onboarding.ApplicationIn, request: Request):
    if body.hp:
        return {"ok": True}
    if not _rate_ok("alta:" + _client_ip(request), limit=3):
        raise HTTPException(429, "Demasiados envíos. Prueba en unos minutos.")
    if not body.acepta:
        raise HTTPException(400, "Necesitamos tu consentimiento para tratar estos datos.")
    if body.email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", body.email):
        raise HTTPException(400, "Revisa el email.")
    row = onboarding.application_row(body)
    db = _db(request)
    if db.recent_application(row["phone"], now() - 600):
        return {"ok": True}
    app_id = db.add_application(row)
    await notify_owner(f"📋 Nueva ficha de alta\nClínica: {row['clinic_name']}\n"
                       f"Contacto: {row['contact_name'] or '-'} · {row['phone']}\n"
                       f"Servicios: {len(row['servicios'])}\nRevisar: {settings.public_base_url}/admin")
    return {"ok": True, "id": app_id}


# ------------------------------------------------------------------- admin
def _admin(authorization: str) -> None:
    if not settings.admin_token:
        raise HTTPException(503, "Define ADMIN_TOKEN para usar el panel de administración")
    if not secrets.compare_digest(authorization.removeprefix("Bearer ").strip(), settings.admin_token):
        raise HTTPException(401, "Token no válido")


@app.get("/api/admin/resumen")
def admin_summary(request: Request, authorization: str = Header("")):
    _admin(authorization)
    db = _db(request)
    since = now() - 30 * 86400
    clinics = []
    for c in db.list_clinics():
        clinics.append({
            "id": c["id"], "nombre": c["nombre"], "activa": c["activa"],
            "faltan": onboarding.missing_config(c), "stats_30d": db.clinic_stats(c["id"], since),
            "panel_token": c.get("panel_token"),
        })
    return {"leads": db.list_leads(), "altas": db.list_applications(), "clinicas": clinics}


@app.get("/api/admin/altas/{app_id}/vista-previa")
def admin_application_preview(app_id: int, request: Request, authorization: str = Header("")):
    """Lo que leería el asistente si se crea la clínica con esta ficha."""
    _admin(authorization)
    a = _db(request).get_application(app_id)
    if not a:
        raise HTTPException(404)
    return {"informacion": onboarding.build_informacion(a), "instrucciones": onboarding.build_instrucciones(a)}


@app.post("/api/admin/altas/{app_id}/convertir")
def admin_convert(app_id: int, request: Request, authorization: str = Header("")):
    _admin(authorization)
    db = _db(request)
    a = db.get_application(app_id)
    if not a:
        raise HTTPException(404)
    if a.get("clinic_id") and db.get_clinic(a["clinic_id"]):
        raise HTTPException(409, f"Ya se creó la clínica {a['clinic_id']}")
    clinic = onboarding.clinic_from_application(a, db.unique_clinic_id(a["clinic_name"]))
    db.upsert_clinic(clinic, overwrite=False)
    db.set_application_status(app_id, "convertida", clinic["id"])
    return {"ok": True, "clinica_id": clinic["id"], "panel_token": clinic["panel_token"],
            "faltan": onboarding.missing_config(clinic)}


class StatusIn(BaseModel):
    estado: str = Field(..., pattern="^[a-z_]{2,20}$")


@app.post("/api/admin/altas/{app_id}/estado")
def admin_application_status(app_id: int, body: StatusIn, request: Request, authorization: str = Header("")):
    _admin(authorization)
    _db(request).set_application_status(app_id, body.estado)
    return {"ok": True}


@app.post("/api/admin/leads/{lead_id}/estado")
def admin_lead_status(lead_id: int, body: StatusIn, request: Request, authorization: str = Header("")):
    _admin(authorization)
    _db(request).set_lead_status(lead_id, body.estado)
    return {"ok": True}


class ActiveIn(BaseModel):
    activa: bool


@app.post("/api/admin/clinicas/{clinic_id}/activa")
def admin_clinic_active(clinic_id: str, body: ActiveIn, request: Request, authorization: str = Header("")):
    _admin(authorization)
    db = _db(request)
    c = db.get_clinic(clinic_id)
    if not c:
        raise HTTPException(404)
    if body.activa and onboarding.missing_config(c):
        raise HTTPException(400, "Antes de activarla falta: " + ", ".join(onboarding.missing_config(c)))
    db.set_clinic_active(clinic_id, body.activa)
    return {"ok": True}


# ------------------------------------------------------------------- panel
def _panel_clinic(request: Request, authorization: str) -> Dict:
    token = authorization.removeprefix("Bearer ").strip()
    if token:
        for c in _db(request).list_clinics():
            if c.get("panel_token") and secrets.compare_digest(token, c["panel_token"]):
                return c
    raise HTTPException(401, "Token no válido")


def _own_conversation(request: Request, clinic: Dict, conv_id: int) -> Dict:
    conv = _db(request).get_conversation(conv_id)
    if not conv or conv["clinic_id"] != clinic["id"]:
        raise HTTPException(404)
    return conv


@app.get("/api/panel/resumen")
def panel_summary(request: Request, authorization: str = Header("")):
    c = _panel_clinic(request, authorization)
    db = _db(request)
    return {"clinica": c["nombre"], "conversaciones": db.list_conversations(c["id"]),
            "solicitudes": db.list_requests(c["id"])}


@app.get("/api/panel/conversaciones/{conv_id}")
def panel_messages(conv_id: int, request: Request, authorization: str = Header("")):
    c = _panel_clinic(request, authorization)
    conv = _own_conversation(request, c, conv_id)
    return {"conversacion": conv, "mensajes": _db(request).history(conv_id, 500)}


class ReplyIn(BaseModel):
    texto: str = Field(..., min_length=1, max_length=4000)


@app.post("/api/panel/conversaciones/{conv_id}/responder")
async def panel_reply(conv_id: int, body: ReplyIn, request: Request, authorization: str = Header("")):
    c = _panel_clinic(request, authorization)
    conv = _own_conversation(request, c, conv_id)
    # Meta solo deja escribir texto libre en las 24 h siguientes al último
    # mensaje del paciente.
    if not conv["last_patient_at"] or now() - conv["last_patient_at"] > 24 * 3600:
        raise HTTPException(409, "Han pasado más de 24 h desde el último mensaje del paciente: llámale.")
    res = await whatsapp.send_text(c.get("wa_phone_number_id", ""), conv["phone"], body.texto)
    if not res.ok:
        raise HTTPException(502, f"WhatsApp no aceptó el mensaje: {res.error}")
    db = _db(request)
    db.add_message(conv_id, "staff", body.texto, wa_id=res.wa_id)
    db.update_conversation(conv_id, mode="human", human_until=now() + settings.human_takeover_s,
                           reply_due_at=None, open=1)
    return {"ok": True}


class ModeIn(BaseModel):
    modo: str = Field(..., pattern="^(bot|human|cerrar)$")


@app.post("/api/panel/conversaciones/{conv_id}/modo")
def panel_mode(conv_id: int, body: ModeIn, request: Request, authorization: str = Header("")):
    c = _panel_clinic(request, authorization)
    _own_conversation(request, c, conv_id)
    db = _db(request)
    if body.modo == "cerrar":
        db.update_conversation(conv_id, open=0, reply_due_at=None)
    elif body.modo == "bot":
        db.update_conversation(conv_id, mode="bot", human_until=None, status="abierta")
    else:
        db.update_conversation(conv_id, mode="human", human_until=now() + settings.human_takeover_s,
                               reply_due_at=None)
    return {"ok": True}


@app.post("/api/panel/solicitudes/{req_id}/hecha")
def panel_request_done(req_id: int, request: Request, authorization: str = Header("")):
    c = _panel_clinic(request, authorization)
    _db(request).close_request(c["id"], req_id)
    return {"ok": True}


# ------------------------------------------------------------ simulador
# Solo funciona mientras WhatsApp está en modo simulación (sin WA_TOKEN). Sirve
# para probar el agente de verdad (con Gemini y la ficha real de una clínica)
# antes de conectar Meta. Lo usa la pestaña "Probar" de /admin.
class DevIn(BaseModel):
    clinica_id: str
    telefono: str = Field(..., min_length=6, max_length=30)
    texto: Optional[str] = Field(None, max_length=2000)


def _dev_guard(authorization: str) -> None:
    _admin(authorization)
    if not whatsapp.dry_run:
        raise HTTPException(409, "El simulador solo funciona sin WA_TOKEN: con WhatsApp real, prueba desde tu móvil.")


def _dev_clinic(request: Request, clinic_id: str) -> Dict:
    clinic = _db(request).get_clinic(clinic_id)
    if not clinic:
        raise HTTPException(404, "Clínica no encontrada")
    return clinic


def _dev_state(db: Database, clinic: Dict, phone: str) -> Dict:
    conv = db.last_conversation(clinic["id"], phone)
    if not conv:
        return {}
    reqs = [r for r in db.list_requests(clinic["id"], only_open=False) if r["conversation_id"] == conv["id"]]
    return {"modo": conv["mode"], "estado": conv["status"], "abierta": bool(conv["open"]),
            "solicitudes": [{"tipo": r["kind"], "nombre": r["name"], "detalle": r["detail"],
                             "preferencia": r["preference"]} for r in reqs]}


@app.post("/api/dev/llamada")
async def dev_call(body: DevIn, request: Request, authorization: str = Header("")):
    """Simula una llamada perdida y la procesa al momento (sin esperar ni franja horaria)."""
    _dev_guard(authorization)
    db = _db(request)
    clinic = _dev_clinic(request, body.clinica_id)
    phone = normalize(body.telefono)
    ref = f"sim-{time.time()}"
    r = service.register_missed_call(db, clinic, phone, ref)
    if r != "registrada":
        return {"resultado": r, "mensajes": [], "estado": _dev_state(db, clinic, phone)}
    call = db._one("SELECT * FROM {T}missed_calls WHERE clinic_id = ? AND call_ref = ?", (clinic["id"], ref))
    r = await service.process_missed_call(db, call, now(), simulate=True)
    msgs = [service.template_text(clinic)] if r == "enviado" else []
    return {"resultado": r, "mensajes": msgs, "estado": _dev_state(db, clinic, phone)}


@app.post("/api/dev/mensaje")
async def dev_message(body: DevIn, request: Request, authorization: str = Header("")):
    """Simula que el paciente escribe y devuelve lo que contestaría el agente."""
    _dev_guard(authorization)
    from app.whatsapp import Inbound
    db = _db(request)
    clinic = _dev_clinic(request, body.clinica_id)
    phone = normalize(body.telefono)
    before = len(whatsapp.outbox)
    ev = Inbound(kind="message", phone_number_id=clinic.get("wa_phone_number_id", ""), phone=phone,
                 wa_id=f"sim-{time.time()}", text=body.texto, media_type="text")
    r = await service.handle_inbound(db, request.app.state.agent, ev, clinic=clinic, allow_inactive=True)
    conv = db.open_conversation(clinic["id"], phone)
    if conv and conv["reply_due_at"]:
        await service.process_reply(db, request.app.state.agent, conv)
    msgs = [m.get("text", {}).get("body") for m in whatsapp.outbox[before:]]
    return {"resultado": r, "mensajes": [m for m in msgs if m], "estado": _dev_state(db, clinic, phone)}


@app.post("/api/dev/reiniciar")
def dev_reset(body: DevIn, request: Request, authorization: str = Header("")):
    """Cierra la conversación simulada y quita la baja, para empezar de cero."""
    _dev_guard(authorization)
    db = _db(request)
    clinic = _dev_clinic(request, body.clinica_id)
    phone = normalize(body.telefono)
    db._exec("UPDATE {T}conversations SET open = 0, reply_due_at = NULL WHERE clinic_id = ? AND phone = ?",
             (clinic["id"], phone))
    db._exec("DELETE FROM {T}optouts WHERE clinic_id = ? AND phone = ?", (clinic["id"], phone))
    db._exec("UPDATE {T}missed_calls SET status = 'omitido', reason = 'simulador reiniciado' "
             "WHERE clinic_id = ? AND phone = ? AND status = 'pendiente'", (clinic["id"], phone))
    return {"ok": True}
