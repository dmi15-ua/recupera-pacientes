"""Entrada de llamadas: Twilio o cualquier centralita que mande un webhook.

Twilio (opción para clínicas con línea tradicional):
  la clínica desvía su número a un número de Twilio cuando no contesta, o los
  pacientes llaman al de Twilio y éste pasa la llamada a recepción con <Dial>.
  Al acabar, Twilio llama a /webhooks/twilio/fin con DialCallStatus. OJO: el
  CallStatus de la llamada principal llega como 'completed' aunque nadie
  descolgara; lo que vale es DialCallStatus.

Centralita en la nube (Aircall, Zadarma, 3CX...): POST /webhooks/llamada con
  {"to": número llamado, "from": paciente, "id": id de la llamada,
   "estado": "perdida" | "atendida"} y la cabecera X-Webhook-Token.
"""
import base64
import hashlib
import hmac
from typing import Dict
from xml.sax.saxutils import escape

from app.config import settings

# Todo lo que no sea 'completed' es que el paciente se quedó sin hablar con nadie.
# 'canceled' = colgó mientras sonaba, el caso más típico.
DIAL_MISSED = {"no-answer", "busy", "failed", "canceled"}


def twilio_signature_ok(url: str, params: Dict[str, str], signature: str) -> bool:
    """Algoritmo de Twilio: HMAC-SHA1 de URL + parámetros ordenados, en base64."""
    if not settings.twilio_auth_token or not signature:
        return False
    data = url + "".join(k + params[k] for k in sorted(params))
    digest = hmac.new(settings.twilio_auth_token.encode(), data.encode(), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


def twiml(inner: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{inner}</Response>'


def twiml_dial(number: str, action_url: str, timeout: int) -> str:
    return twiml(f'<Dial timeout="{timeout}" action="{escape(action_url)}" method="POST">{escape(number)}</Dial>')


def twiml_say_and_hangup(text: str) -> str:
    return twiml(f'<Say language="es-ES">{escape(text)}</Say><Hangup/>')


DEFAULT_MISSED_SAY = ("Ahora mismo no podemos atenderte. En unos minutos te escribiremos "
                      "por WhatsApp a este número para ayudarte. Gracias.")
