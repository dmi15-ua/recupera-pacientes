"""Reglas de negocio: qué hacer con cada llamada perdida y cada mensaje.

Los webhooks solo registran y devuelven 200 al momento. El trabajo pesado
(enviar la plantilla, llamar al LLM) lo hace el bucle de `worker`, que así
puede esperar, agrupar y descartar sin bloquear a Meta ni a la centralita.
"""
import logging
from typing import Any, Dict, Optional

from app import hours, safety
from app.agent import Agent
from app.config import settings
from app.db import Database, now
from app.llm import llm
from app.notify import notify_clinic
from app.phone import is_reachable_number, is_spanish_landline, normalize
from app.whatsapp import Inbound, b64, whatsapp

log = logging.getLogger(__name__)

OPTOUT_REPLY = "Hecho, no volveremos a escribirte por aquí. Si nos necesitas, aquí estamos."
NO_TEXT_REPLY = ("Perdona, solo puedo leer mensajes de texto y notas de voz. "
                 "¿Me lo puedes escribir en un mensaje?")

DEFAULT_TEMPLATE_TEXT = (
    "Hola, somos {clinica}. Hemos visto tu llamada y no hemos podido atenderte. "
    "¿En qué te podemos ayudar? Responde a este mensaje y te atendemos por aquí. "
    "Si no quieres recibir mensajes, responde BAJA."
)


def _mask(phone: str) -> str:
    """En los logs no van teléfonos completos."""
    return phone[:4] + "****" + phone[-2:] if len(phone) > 6 else "****"


# ------------------------------------------------------------ llamadas perdidas
def register_missed_call(db: Database, clinic: Dict[str, Any], raw_phone: str, call_ref: str) -> str:
    phone = normalize(raw_phone)
    if not is_reachable_number(phone):
        return "omitida: número oculto o no válido"
    send_after = hours.next_send_time(clinic, now() + settings.missed_call_delay_s)
    call_id = db.add_missed_call(clinic["id"], phone, call_ref, send_after)
    if call_id is None:
        return "duplicada"
    log.info("Llamada perdida %s en %s (envío a partir de %s)", _mask(phone), clinic["id"], send_after)
    return "registrada"


def register_answered_call(db: Database, clinic: Dict[str, Any], raw_phone: str) -> int:
    """El paciente volvió a llamar y le cogieron: no hace falta escribirle."""
    return db.cancel_pending_missed(clinic["id"], normalize(raw_phone), "llamada atendida después")


def template_text(clinic: Dict[str, Any]) -> str:
    tpl = clinic.get("plantilla", {})
    return tpl.get("texto", DEFAULT_TEMPLATE_TEXT).replace("{clinica}", clinic["nombre"])


async def process_missed_call(db: Database, call: Dict[str, Any], t: int) -> str:
    clinic = db.get_clinic(call["clinic_id"])
    phone = call["phone"]

    def skip(reason: str) -> str:
        db.set_missed_status(call["id"], "omitido", reason)
        return f"omitido: {reason}"

    if not clinic or not clinic.get("activa", True):
        return skip("clínica inactiva")
    if db.is_opted_out(clinic["id"], phone):
        return skip("el paciente pidió la baja")
    if phone in {normalize(n) for n in clinic.get("bloqueados", [])}:
        return skip("número bloqueado")

    # Puede que la franja de envío se haya cerrado mientras esperaba.
    allowed = hours.next_send_time(clinic, t)
    if allowed > t:
        db.set_missed_status(call["id"], "pendiente", send_after=allowed)
        return "aplazado"

    if db.recent_sent_missed(clinic["id"], phone, t - settings.collapse_window_s):
        return skip("ya se le escribió por otra llamada reciente")

    last = db.last_conversation(clinic["id"], phone)
    if last and last["open"] and last["updated_at"] >= t - settings.recent_conversation_s:
        return skip("ya hay una conversación reciente")

    if is_spanish_landline(phone):
        db.set_missed_status(call["id"], "fallido", "es un fijo (sin WhatsApp)")
        await _ask_callback(db, clinic, phone, "Llamó desde un fijo: no se le puede escribir por WhatsApp")
        return "fallido: fijo"

    tpl = clinic.get("plantilla", {})
    res = await whatsapp.send_template(
        clinic["wa_phone_number_id"], phone,
        tpl.get("nombre", "llamada_perdida"), tpl.get("idioma", "es"),
        [clinic["nombre"]] if tpl.get("con_nombre_clinica", True) else [],
    )
    if not res.ok:
        db.set_missed_status(call["id"], "fallido", res.error)
        await _ask_callback(db, clinic, phone, f"No se pudo enviar el WhatsApp ({res.error})")
        return "fallido"

    db.set_missed_status(call["id"], "enviado", wa_id=res.wa_id)
    conv = db.get_or_open_conversation(clinic["id"], phone, origin="llamada_perdida")
    db.add_message(conv["id"], "bot", template_text(clinic), wa_id=res.wa_id)
    # Otras llamadas del mismo número en cola: ya está cubierto.
    db.cancel_pending_missed(clinic["id"], phone, "agrupada con otra llamada")
    return "enviado"


async def _ask_callback(db: Database, clinic: Dict[str, Any], phone: str, reason: str) -> None:
    conv = db.get_or_open_conversation(clinic["id"], phone, origin="llamada_perdida")
    db.add_request(clinic["id"], conv["id"], "llamar", phone, detail=reason)
    await notify_clinic(clinic, "📞 Devolver llamada", {"Teléfono": phone, "Motivo": reason})


# ------------------------------------------------------------- mensajes entrantes
async def _transcribe(media_id: str, mime: str) -> Optional[str]:
    if not settings.transcribe_audio:
        return None
    audio = await whatsapp.download_media(media_id)
    if not audio:
        return None
    mime = (mime or "audio/ogg").split(";")[0]
    resp = await llm.generate(
        "Transcribes notas de voz de pacientes. Devuelve solo el texto dicho, sin comentarios.",
        [{"role": "user", "parts": [{"inlineData": {"mimeType": mime, "data": b64(audio)}},
                                    {"text": "Transcribe esta nota de voz."}]}],
        max_tokens=1024,
    )
    return resp.text if resp.ok and resp.text else None


async def handle_inbound(db: Database, agent: Agent, ev: Inbound) -> str:
    clinic = db.clinic_by_wa_number(ev.phone_number_id)
    if not clinic:
        return "ignorado: número de WhatsApp sin clínica"

    if ev.kind == "status":
        return await _handle_status(db, clinic, ev)

    if ev.wa_id and db.message_seen(ev.wa_id):
        return "duplicado"

    if ev.kind == "echo":
        conv = db.get_or_open_conversation(clinic["id"], ev.phone, origin="whatsapp")
        db.add_message(conv["id"], "staff", ev.text or "", wa_id=ev.wa_id)
        db.update_conversation(conv["id"], mode="human", human_until=now() + settings.human_takeover_s,
                               reply_due_at=None)
        return "recepción tomó la conversación"

    conv = db.get_or_open_conversation(clinic["id"], ev.phone, origin="whatsapp", name=ev.name)
    db.cancel_pending_missed(clinic["id"], ev.phone, "el paciente ya escribió")

    text = ev.text
    if not text and ev.media_type == "audio" and ev.media_id:
        transcript = await _transcribe(ev.media_id, ev.media_mime)
        text = f"(nota de voz) {transcript}" if transcript else None
    if not text:
        db.add_message(conv["id"], "patient", f"[{ev.media_type or 'mensaje'} sin texto]", wa_id=ev.wa_id)
        db.update_conversation(conv["id"], last_patient_at=now())
        await _reply_fixed(db, clinic, conv, NO_TEXT_REPLY)
        return "sin texto"

    if not db.add_message(conv["id"], "patient", text, wa_id=ev.wa_id or None):
        return "duplicado"
    db.update_conversation(conv["id"], last_patient_at=now())

    if safety.is_optout(text):
        db.add_optout(clinic["id"], ev.phone)
        await _reply_fixed(db, clinic, conv, OPTOUT_REPLY)
        db.update_conversation(conv["id"], open=0, reply_due_at=None)
        return "baja"

    if safety.is_red_flag(text):
        db.add_request(clinic["id"], conv["id"], "urgencia", ev.phone, name=conv.get("name"), detail=text[:300])
        db.update_conversation(conv["id"], mode="human", status="urgencia", reply_due_at=None,
                               human_until=now() + settings.human_takeover_s)
        await _reply_fixed(db, clinic, conv, safety.EMERGENCY_REPLY)
        await notify_clinic(clinic, "🚨 URGENCIA (posible riesgo vital)", {
            "Paciente": conv.get("name"), "Teléfono": ev.phone, "Mensaje": text[:300],
        })
        return "urgencia"

    if conv["mode"] == "human" and (conv["human_until"] or 0) > now():
        return "en manos de recepción"

    # Se espera unos segundos: si el paciente manda tres mensajes seguidos, se
    # contesta una sola vez a los tres.
    db.update_conversation(conv["id"], mode="bot", reply_due_at=now() + settings.debounce_s)
    return "respuesta programada"


async def _handle_status(db: Database, clinic: Dict[str, Any], ev: Inbound) -> str:
    if ev.status != "failed":
        return "estado"
    call = db.missed_by_wa_id(ev.wa_id)
    if call and call["status"] == "enviado":
        db.set_missed_status(call["id"], "fallido", f"WhatsApp no entregó el mensaje ({ev.error_code})")
        await _ask_callback(db, clinic, call["phone"],
                            "El WhatsApp no se pudo entregar (puede que no tenga WhatsApp)")
        return "plantilla no entregada"
    return "mensaje no entregado"


async def _reply_fixed(db: Database, clinic: Dict[str, Any], conv: Dict[str, Any], text: str) -> None:
    res = await whatsapp.send_text(clinic["wa_phone_number_id"], conv["phone"], text)
    db.add_message(conv["id"], "bot", text, wa_id=res.wa_id if res.ok else None)


async def process_reply(db: Database, agent: Agent, conv: Dict[str, Any]) -> str:
    db.update_conversation(conv["id"], reply_due_at=None)
    conv = db.get_conversation(conv["id"])
    if conv["mode"] == "human" and (conv["human_until"] or 0) > now():
        return "en manos de recepción"
    clinic = db.get_clinic(conv["clinic_id"])
    if not clinic:
        return "sin clínica"
    result = await agent.respond(clinic, conv)
    await _reply_fixed(db, clinic, conv, result.reply)
    return "respondido"


# --------------------------------------------------------------------- bucle
async def tick(db: Database, agent: Agent, t: Optional[int] = None) -> None:
    t = t or now()
    for call in db.due_missed_calls(t):
        try:
            await process_missed_call(db, call, t)
        except Exception:
            log.exception("Error procesando la llamada perdida %s", call["id"])
            db.set_missed_status(call["id"], "fallido", "error interno")
    for conv in db.due_conversations(t):
        try:
            await process_reply(db, agent, conv)
        except Exception:
            log.exception("Error respondiendo la conversación %s", conv["id"])


def maintenance(db: Database, t: Optional[int] = None) -> None:
    t = t or now()
    closed = db.close_idle(t - settings.idle_close_s)
    cutoff = t - settings.retention_days * 86400
    purged = db.purge_old_messages(cutoff)
    db._exec("DELETE FROM requests WHERE created_at < ?", (cutoff,))
    db._exec("DELETE FROM missed_calls WHERE received_at < ?", (cutoff,))
    if closed or purged:
        log.info("Mantenimiento: %s conversaciones cerradas, %s borradas por antigüedad", closed, purged)
