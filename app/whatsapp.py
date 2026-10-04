"""WhatsApp Cloud API oficial de Meta.

Por qué la oficial y no Evolution/Baileys: no bloquean el número, se puede
vender a clínicas sin incumplir las condiciones de WhatsApp y los mensajes que
inicia el paciente son gratis. Lo único que se paga es la plantilla del primer
mensaje tras la llamada perdida (céntimos).

Sin WA_TOKEN el cliente no envía nada: guarda los mensajes en `outbox` y los
imprime, para probar todo en local sin coste.
"""
import base64
import hashlib
import hmac
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.phone import normalize, to_wa

log = logging.getLogger(__name__)


@dataclass
class SendResult:
    ok: bool
    wa_id: Optional[str] = None
    error: str = ""
    error_code: Optional[int] = None


@dataclass
class Inbound:
    """Mensaje o evento entrante ya simplificado."""
    kind: str                      # message | echo | status
    phone_number_id: str
    phone: str                     # el paciente, en E.164
    wa_id: str = ""
    text: Optional[str] = None
    name: Optional[str] = None
    media_id: Optional[str] = None
    media_mime: Optional[str] = None
    media_type: Optional[str] = None
    status: Optional[str] = None
    error_code: Optional[int] = None


class WhatsAppClient:
    def __init__(self):
        self.outbox: List[Dict[str, Any]] = []

    @property
    def dry_run(self) -> bool:
        return not settings.wa_token

    def _url(self, path: str) -> str:
        return f"https://graph.facebook.com/{settings.wa_graph_version}/{path}"

    async def _post(self, phone_number_id: str, payload: Dict[str, Any]) -> SendResult:
        if self.dry_run:
            # En un servidor el simulador puede correr días: no dejar crecer la lista.
            if len(self.outbox) > 1000:
                del self.outbox[:500]
            self.outbox.append({"phone_number_id": phone_number_id, **payload})
            body = payload.get("text", {}).get("body") or f"[plantilla {payload.get('template', {}).get('name')}]"
            log.info("[WhatsApp simulado] a %s", payload["to"][:4] + "****")
            # Id único de verdad: uno basado en un contador se repetía tras cada
            # reinicio, chocaba con los ya guardados y la respuesta no se guardaba.
            return SendResult(ok=True, wa_id=f"sim-{uuid.uuid4().hex}")
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    self._url(f"{phone_number_id}/messages"),
                    headers={"Authorization": f"Bearer {settings.wa_token}"},
                    json=payload,
                )
            data = r.json() if r.content else {}
            if r.status_code == 200 and data.get("messages"):
                return SendResult(ok=True, wa_id=data["messages"][0]["id"])
            err = data.get("error", {})
            log.error("WhatsApp rechazó el envío (%s): %s", r.status_code, err.get("message", r.text[:200]))
            return SendResult(ok=False, error=err.get("message", f"HTTP {r.status_code}"), error_code=err.get("code"))
        except httpx.HTTPError as e:
            log.error("Error de red con WhatsApp: %s", e)
            return SendResult(ok=False, error=str(e))

    async def send_text(self, phone_number_id: str, to: str, body: str) -> SendResult:
        return await self._post(phone_number_id, {
            "messaging_product": "whatsapp",
            "to": to_wa(to),
            "type": "text",
            "text": {"body": body[:4000], "preview_url": False},
        })

    async def send_template(self, phone_number_id: str, to: str, name: str, lang: str,
                            params: List[str]) -> SendResult:
        template: Dict[str, Any] = {"name": name, "language": {"code": lang}}
        if params:
            template["components"] = [{
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in params],
            }]
        return await self._post(phone_number_id, {
            "messaging_product": "whatsapp",
            "to": to_wa(to),
            "type": "template",
            "template": template,
        })

    async def download_media(self, media_id: str) -> Optional[bytes]:
        if self.dry_run:
            return None
        headers = {"Authorization": f"Bearer {settings.wa_token}"}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                meta = await client.get(self._url(media_id), headers=headers)
                url = meta.json().get("url")
                if not url:
                    return None
                media = await client.get(url, headers=headers)
                # Una nota de voz normal pesa < 1 MB. Se corta en 10 MB para
                # no mandar al LLM algo enorme (y caro).
                if media.status_code != 200 or len(media.content) > 10_000_000:
                    return None
                return media.content
        except httpx.HTTPError as e:
            log.error("No se pudo descargar el audio: %s", e)
            return None


def verify_signature(raw_body: bytes, header: Optional[str]) -> bool:
    """Comprueba X-Hub-Signature-256: solo Meta conoce el app secret."""
    if not settings.wa_app_secret:
        return False
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(settings.wa_app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[7:])


def _text_of(msg: Dict[str, Any]) -> Optional[str]:
    t = msg.get("type")
    if t == "text":
        return msg.get("text", {}).get("body")
    if t == "button":
        return msg.get("button", {}).get("text")
    if t == "interactive":
        inter = msg.get("interactive", {})
        return (inter.get("button_reply") or inter.get("list_reply") or {}).get("title")
    if t in ("image", "video", "document"):
        return msg.get(t, {}).get("caption")
    return None


def parse_webhook(body: Dict[str, Any]) -> List[Inbound]:
    """Convierte el JSON de Meta en una lista de eventos simples."""
    events: List[Inbound] = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            pnid = value.get("metadata", {}).get("phone_number_id", "")
            names = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}

            for msg in value.get("messages", []):
                t = msg.get("type")
                media = msg.get(t, {}) if t in ("audio", "image", "video", "document") else {}
                events.append(Inbound(
                    kind="message",
                    phone_number_id=pnid,
                    phone=normalize(msg.get("from")),
                    wa_id=msg.get("id", ""),
                    text=_text_of(msg),
                    name=names.get(msg.get("from")),
                    media_id=media.get("id"),
                    media_mime=media.get("mime_type"),
                    media_type=t,
                ))

            # Coexistencia: recepción contesta desde la app WhatsApp Business del
            # móvil y Meta nos manda una copia. Así el bot sabe que debe callar.
            for echo in value.get("message_echoes", []):
                events.append(Inbound(
                    kind="echo",
                    phone_number_id=pnid,
                    phone=normalize(echo.get("to")),
                    wa_id=echo.get("id", ""),
                    text=_text_of(echo) or f"[{echo.get('type', 'mensaje')}]",
                ))

            for st in value.get("statuses", []):
                errors = st.get("errors") or [{}]
                events.append(Inbound(
                    kind="status",
                    phone_number_id=pnid,
                    phone=normalize(st.get("recipient_id")),
                    wa_id=st.get("id", ""),
                    status=st.get("status"),
                    error_code=errors[0].get("code"),
                ))
    return events


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


whatsapp = WhatsAppClient()
