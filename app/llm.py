"""Cliente mínimo de Gemini con function calling, sobre la API REST.

Se elige Gemini Flash-Lite porque es de los modelos más baratos del mercado y
para un WhatsApp de clínica sobra. Importante: usar una API key de un proyecto
CON facturación activada. En el nivel gratuito Google puede usar el contenido
para mejorar sus productos, y aquí hay datos de salud.

La key va en la cabecera x-goog-api-key, nunca en la URL: httpx registra las
URLs en el log y la clave acabaría en los logs del servidor.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings

log = logging.getLogger(__name__)

BASE = "https://generativelanguage.googleapis.com/v1beta/models"


@dataclass
class LLMResponse:
    ok: bool
    parts: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    @property
    def text(self) -> str:
        return "".join(p.get("text", "") for p in self.parts if not p.get("thought")).strip()

    @property
    def calls(self) -> List[Tuple[str, Dict[str, Any]]]:
        return [(p["functionCall"]["name"], p["functionCall"].get("args") or {})
                for p in self.parts if "functionCall" in p]


class GeminiClient:
    async def generate(self, system: str, contents: List[Dict[str, Any]],
                       tools: Optional[List[Dict[str, Any]]] = None,
                       max_tokens: int = 1024) -> LLMResponse:
        if not settings.gemini_api_key:
            return LLMResponse(ok=False, error="sin GEMINI_API_KEY")

        payload: Dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            # Margen amplio: si el modelo razona por dentro, esos tokens salen
            # de aquí y con poco margen la respuesta llegaría cortada. Solo se
            # paga lo que se genera, no el máximo.
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": max_tokens},
        }
        if tools:
            payload["tools"] = [{"functionDeclarations": tools}]

        for attempt in (1, 2):
            try:
                async with httpx.AsyncClient(timeout=40) as client:
                    r = await client.post(
                        f"{BASE}/{settings.gemini_model}:generateContent",
                        headers={"x-goog-api-key": settings.gemini_api_key},
                        json=payload,
                    )
            except httpx.HTTPError as e:
                log.warning("Gemini: error de red (intento %s): %s", attempt, e)
                continue

            if r.status_code == 200:
                data = r.json()
                cands = data.get("candidates") or []
                if not cands:
                    return LLMResponse(ok=False, error="sin candidatos (bloqueado)")
                parts = cands[0].get("content", {}).get("parts", [])
                finish = cands[0].get("finishReason")
                if finish == "MAX_TOKENS" and not any("functionCall" in p for p in parts):
                    return LLMResponse(ok=False, parts=parts, error="respuesta cortada")
                return LLMResponse(ok=True, parts=parts)

            # 429 = cuota agotada, 4xx = petición mala: reintentar no arregla nada.
            if r.status_code < 500:
                log.error("Gemini rechazó la petición (%s): %s", r.status_code, r.text[:300])
                return LLMResponse(ok=False, error=f"HTTP {r.status_code}")
            log.warning("Gemini: error %s (intento %s)", r.status_code, attempt)

        return LLMResponse(ok=False, error="Gemini no disponible")


llm = GeminiClient()
