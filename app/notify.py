"""Avisos a recepción por Telegram.

Telegram es gratis y la recepcionista lo tiene en el móvil al momento. Si no
está configurado, el aviso queda en el log y en el panel (/panel).

Se manda lo mínimo: nombre, teléfono y qué necesita. El detalle de la
conversación se consulta en el panel, no viaja a Telegram.
"""
import logging
from typing import Dict, Optional

import httpx

from app.config import settings

log = logging.getLogger(__name__)

sent: list = []  # para tests y modo local


async def telegram(chat_id: Optional[str], text: str) -> bool:
    if not settings.telegram_bot_token or not chat_id:
        sent.append({"chat_id": chat_id, "text": text})
        log.info("[Aviso sin Telegram] %s", text.replace("\n", " | "))
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            )
        return r.status_code == 200
    except httpx.HTTPError as e:
        log.error("Telegram falló: %s", e)
        return False


async def notify_clinic(clinic: Dict, title: str, lines: Dict[str, Optional[str]]) -> bool:
    body = "\n".join(f"{k}: {v}" for k, v in lines.items() if v)
    link = f"{settings.public_base_url}/panel"
    return await telegram(clinic.get("telegram_chat_id"), f"{title}\n{body}\n\nPanel: {link}")


async def notify_owner(text: str) -> bool:
    return await telegram(settings.owner_telegram_chat_id, text)
