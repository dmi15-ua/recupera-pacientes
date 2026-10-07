from datetime import datetime
from zoneinfo import ZoneInfo

from app import hours, safety, service
from app.agent import FALLBACK_REPLY
from app.config import settings
from app.db import now
from app.phone import is_spanish_landline, normalize
from app.whatsapp import Inbound, whatsapp
from app import notify

from conftest import CLINIC, call, run, text


def msg(body, wa_id="w1", phone="+34600111222", pnid="PNID1", **kw):
    return Inbound(kind="message", phone_number_id=pnid, phone=phone, wa_id=wa_id, text=body,
                   media_type="text", **kw)


def bodies():
    return [m.get("text", {}).get("body") or "PLANTILLA:" + m["template"]["name"] for m in whatsapp.outbox]


# ------------------------------------------------------------------ utilidades
def test_normalize_phone():
    assert normalize("600 11 22 33") == "+34600112233"
    assert normalize("34600112233") == "+34600112233"
    assert normalize("0034600112233") == "+34600112233"
    assert normalize("whatsapp:+34600112233") == "+34600112233"
    assert normalize("anonymous") == ""
    assert is_spanish_landline("+34910000000")
    assert not is_spanish_landline("+34600112233")


def test_no_messages_at_night():
    clinic = {**CLINIC, "envio_permitido": "09:00-21:00"}
    tz = ZoneInfo("Europe/Madrid")
    at_23 = int(datetime(2026, 10, 5, 23, 0, tzinfo=tz).timestamp())
    nxt = datetime.fromtimestamp(hours.next_send_time(clinic, at_23), tz)
    assert (nxt.day, nxt.hour, nxt.minute) == (6, 9, 0)
    at_10 = int(datetime(2026, 10, 5, 10, 0, tzinfo=tz).timestamp())
    assert hours.next_send_time(clinic, at_10) == at_10


def test_safety_filters():
    assert safety.is_red_flag("Hola, se me está hinchando la cara y me cuesta respirar")
    assert safety.is_red_flag("NO PARA DE SANGRAR la encía")
    assert not safety.is_red_flag("quería una cita para una limpieza")
    assert safety.is_optout("BAJA")
    assert safety.is_optout("por favor no me escribáis más")
    assert not safety.is_optout("no puedo el martes")


# ----------------------------------------------------------- llamadas perdidas
def test_missed_call_waits_then_sends_template(db, make_agent):
    agent, _ = make_agent()
    assert service.register_missed_call(db, CLINIC, "600111222", "call-1") == "registrada"
    run(service.tick(db, agent, t=now()))
    assert whatsapp.outbox == []  # todavía dentro del margen de espera

    run(service.tick(db, agent, t=now() + settings.missed_call_delay_s + 1))
    assert bodies() == ["PLANTILLA:llamada_perdida"]
    conv = db.open_conversation("c1", "+34600111222")
    assert conv["origin"] == "llamada_perdida"
    assert "Clínica Prueba" in db.history(conv["id"], 5)[0]["content"]


def test_repeated_calls_send_one_message(db, make_agent):
    agent, _ = make_agent()
    service.register_missed_call(db, CLINIC, "600111222", "call-1")
    assert service.register_missed_call(db, CLINIC, "600111222", "call-1") == "duplicada"
    service.register_missed_call(db, CLINIC, "+34 600 111 222", "call-2")
    service.register_missed_call(db, CLINIC, "600111222", "call-3")
    run(service.tick(db, agent, t=now() + 1000))
    assert len(whatsapp.outbox) == 1


def test_answered_call_cancels_message(db, make_agent):
    agent, _ = make_agent()
    service.register_missed_call(db, CLINIC, "600111222", "call-1")
    assert service.register_answered_call(db, CLINIC, "600111222") == 1
    run(service.tick(db, agent, t=now() + 1000))
    assert whatsapp.outbox == []


def test_landline_asks_reception_to_call_back(db, make_agent):
    agent, _ = make_agent()
    service.register_missed_call(db, CLINIC, "912345678", "call-1")
    run(service.tick(db, agent, t=now() + 1000))
    assert whatsapp.outbox == []
    assert db.list_requests("c1")[0]["kind"] == "llamar"
    assert "Devolver llamada" in notify.sent[-1]["text"]


def test_hidden_number_is_ignored(db):
    assert service.register_missed_call(db, CLINIC, "anonymous", "call-1").startswith("omitida")


def test_opted_out_patient_gets_no_template(db, make_agent):
    agent, _ = make_agent()
    run(service.handle_inbound(db, agent, msg("BAJA")))
    assert bodies()[-1] == service.OPTOUT_REPLY
    whatsapp.outbox.clear()
    service.register_missed_call(db, CLINIC, "600111222", "call-1")
    run(service.tick(db, agent, t=now() + 100000))
    assert whatsapp.outbox == []


def test_failed_delivery_asks_for_callback(db, make_agent):
    agent, _ = make_agent()
    service.register_missed_call(db, CLINIC, "600111222", "call-1")
    run(service.tick(db, agent, t=now() + 1000))
    wa_id = db._one("SELECT wa_id FROM {T}missed_calls")["wa_id"]
    ev = Inbound(kind="status", phone_number_id="PNID1", phone="+34600111222", wa_id=wa_id,
                 status="failed", error_code=131026)
    assert run(service.handle_inbound(db, agent, ev)) == "plantilla no entregada"
    assert db.list_requests("c1")[0]["kind"] == "llamar"


# ------------------------------------------------------------------ conversación
def test_patient_message_gets_debounced_reply(db, make_agent):
    agent, llm = make_agent(text("¡Hola! La limpieza cuesta 45 €. ¿Quieres cita?"))
    run(service.handle_inbound(db, agent, msg("hola", "w1")))
    run(service.handle_inbound(db, agent, msg("cuánto cuesta una limpieza", "w2")))
    run(service.tick(db, agent, t=now()))
    assert whatsapp.outbox == []  # aún esperando a que termine de escribir

    run(service.tick(db, agent, t=now() + settings.debounce_s + 1))
    assert bodies() == ["¡Hola! La limpieza cuesta 45 €. ¿Quieres cita?"]
    assert len(llm.calls) == 1  # una sola respuesta para los dos mensajes
    assert "hola\ncuánto cuesta" in llm.calls[0]["contents"][0]["parts"][0]["text"]


def test_duplicate_webhook_is_ignored(db, make_agent):
    agent, _ = make_agent()
    run(service.handle_inbound(db, agent, msg("hola", "w1")))
    assert run(service.handle_inbound(db, agent, msg("hola", "w1"))) == "duplicado"


def test_appointment_request_notifies_reception(db, make_agent):
    agent, llm = make_agent(
        call("registrar_solicitud_cita", nombre="Ana Pérez", motivo="limpieza", preferencia_horario="martes tarde"),
        text("Perfecto, Ana. Recepción te confirmará el hueco por aquí."),
    )
    run(service.handle_inbound(db, agent, msg("Soy Ana Pérez, limpieza, martes tarde")))
    run(service.tick(db, agent, t=now() + 60))

    req = db.list_requests("c1")[0]
    assert (req["kind"], req["name"], req["preference"]) == ("cita", "Ana Pérez", "martes tarde")
    conv = db.open_conversation("c1", "+34600111222")
    assert conv["status"] == "cita_solicitada"
    assert "Solicitud de cita" in notify.sent[-1]["text"]
    # El resultado de la herramienta vuelve al modelo junto con la firma.
    second = llm.calls[1]["contents"]
    assert second[-2]["parts"][0]["thoughtSignature"] == "x"
    assert second[-1]["parts"][0]["functionResponse"]["name"] == "registrar_solicitud_cita"
    assert bodies()[-1].startswith("Perfecto, Ana")


def test_emergency_skips_llm(db, make_agent):
    agent, llm = make_agent(text("no debería usarse"))
    r = run(service.handle_inbound(db, agent, msg("me duele y no puedo respirar bien")))
    assert r == "urgencia"
    assert bodies() == [service.safety.EMERGENCY_REPLY]
    run(service.tick(db, agent, t=now() + 60))
    assert llm.calls == []
    assert "URGENCIA" in notify.sent[-1]["text"]


def test_staff_echo_silences_bot(db, make_agent):
    agent, llm = make_agent(text("no debería usarse"))
    run(service.handle_inbound(db, agent, msg("hola", "w1")))
    echo = Inbound(kind="echo", phone_number_id="PNID1", phone="+34600111222", wa_id="e1", text="Hola, soy Marta")
    run(service.handle_inbound(db, agent, echo))
    run(service.handle_inbound(db, agent, msg("gracias Marta", "w2")))
    run(service.tick(db, agent, t=now() + 60))
    assert llm.calls == [] and whatsapp.outbox == []


def test_llm_failure_hands_off(db, make_agent):
    agent, _ = make_agent()  # sin respuestas = fallo
    run(service.handle_inbound(db, agent, msg("hola")))
    run(service.tick(db, agent, t=now() + 60))
    assert bodies() == [FALLBACK_REPLY]
    conv = db.open_conversation("c1", "+34600111222")
    assert conv["mode"] == "human" and conv["status"] == "requiere_humano"


def test_daily_llm_limit(db, make_agent, monkeypatch):
    monkeypatch.setattr(settings, "max_llm_calls_per_day", 1)
    agent, llm = make_agent(text("uno"), text("dos"))
    run(service.handle_inbound(db, agent, msg("a", "w1")))
    run(service.tick(db, agent, t=now() + 60))
    run(service.handle_inbound(db, agent, msg("b", "w2")))
    run(service.tick(db, agent, t=now() + 120))
    assert len(llm.calls) == 1
    assert db.open_conversation("c1", "+34600111222")["mode"] == "human"


def test_unknown_whatsapp_number_ignored(db, make_agent):
    agent, _ = make_agent()
    assert run(service.handle_inbound(db, agent, msg("hola", pnid="NOPE"))).startswith("ignorado")


def test_bot_replies_survive_restart(db, make_agent):
    """Tras reiniciar el servidor (outbox vacío), las respuestas se siguen guardando."""
    agent, llm = make_agent(text("primera"), text("segunda"))
    run(service.handle_inbound(db, agent, msg("hola", "w1")))
    run(service.tick(db, agent, t=now() + 60))
    whatsapp.outbox.clear()  # como tras un reinicio
    run(service.handle_inbound(db, agent, msg("otra pregunta", "w2")))
    run(service.tick(db, agent, t=now() + 120))
    conv = db.open_conversation("c1", "+34600111222")
    roles = [m["role"] for m in db.history(conv["id"], 10)]
    assert roles == ["patient", "bot", "patient", "bot"]
    # Y el modelo ve su propia respuesta anterior.
    assert llm.calls[1]["contents"][1] == {"role": "model", "parts": [{"text": "primera"}]}


def test_unknown_question_reaches_reception(db, make_agent):
    agent, _ = make_agent(call("anotar_duda", pregunta="¿Tenéis parking?"),
                          text("No tengo ese dato, se lo pregunto al equipo y te contestan por aquí."))
    run(service.handle_inbound(db, agent, msg("¿Tenéis parking?")))
    run(service.tick(db, agent, t=now() + 60))
    req = db.list_requests("c1")[0]
    assert (req["kind"], req["detail"]) == ("duda", "¿Tenéis parking?")
    assert "Pregunta de un paciente" in notify.sent[-1]["text"]
    assert db.open_conversation("c1", "+34600111222")["mode"] == "bot"  # sigue atendiendo


def test_slow_reply_does_not_block_others(db, make_agent):
    """Varias conversaciones se atienden a la vez y quedan sus tiempos registrados."""
    import asyncio
    import time as _time
    agent, llm = make_agent()

    async def slow_generate(system, contents, tools=None, max_tokens=1024):
        await asyncio.sleep(0.4)
        return text("ok")

    llm.generate = slow_generate
    for i in range(4):
        run(service.handle_inbound(db, agent, msg(f"hola {i}", f"w{i}", phone=f"+3460011100{i}")))
    service.TIMINGS.clear()
    t0 = _time.monotonic()
    run(service.tick(db, agent, t=now() + 60))
    assert _time.monotonic() - t0 < 1.2   # en serie serían 1.6 s
    assert len(whatsapp.outbox) == 4 and len(service.TIMINGS) == 4
    assert {"cola_s", "ia_s", "envio_s", "total_s"} <= set(service.TIMINGS[0])
