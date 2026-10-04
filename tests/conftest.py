import asyncio
import os
import sys
import tempfile

# La configuración se lee al importar: hay que fijar el entorno antes.
_tmp = tempfile.mkdtemp()
os.environ.update({
    "DATABASE_PATH": os.path.join(_tmp, "test.db"),
    "CLINICS_FILE": os.path.join(_tmp, "no-existe.json"),
    "PUBLIC_BASE_URL": "https://test.local",
    "WA_TOKEN": "",
    "WA_APP_SECRET": "secreto-app",
    "WA_VERIFY_TOKEN": "verificame",
    "GEMINI_API_KEY": "",
    "TWILIO_AUTH_TOKEN": "twilio-token",
    "CALL_WEBHOOK_TOKEN": "token-centralita",
    "TELEGRAM_BOT_TOKEN": "",
    "ADMIN_TOKEN": "admin",
    "DISABLE_WORKER": "1",
})
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from app import notify  # noqa: E402
from app.agent import Agent  # noqa: E402
from app.db import Database  # noqa: E402
from app.llm import LLMResponse  # noqa: E402
from app.whatsapp import whatsapp  # noqa: E402

CLINIC = {
    "id": "c1",
    "nombre": "Clínica Prueba",
    "asistente": "Laura",
    "wa_phone_number_id": "PNID1",
    "numeros_llamada": ["+34910000000"],
    "telefono_recepcion": "+34910000001",
    "horario": {d: ["09:00-20:00"] for d in ["lun", "mar", "mie", "jue", "vie"]},
    "envio_permitido": "00:00-24:00",
    "informacion": "Limpieza: 45 €.",
    "panel_token": "panel-c1",
}
OTHER = {**CLINIC, "id": "c2", "nombre": "Otra", "wa_phone_number_id": "PNID2",
         "numeros_llamada": ["+34920000000"], "panel_token": "panel-c2"}


class FakeLLM:
    """Devuelve respuestas preparadas y apunta lo que se le pidió."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def generate(self, system, contents, tools=None, max_tokens=1024):
        self.calls.append({"system": system, "contents": [dict(c) for c in contents]})
        if not self.responses:
            return LLMResponse(ok=False, error="sin respuestas preparadas")
        return self.responses.pop(0)


def text(t):
    return LLMResponse(ok=True, parts=[{"text": t}])


def call(name, **args):
    return LLMResponse(ok=True, parts=[{"functionCall": {"name": name, "args": args}, "thoughtSignature": "x"}])


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db():
    d = Database(":memory:")
    d.upsert_clinic(CLINIC)
    d.upsert_clinic(OTHER)
    whatsapp.outbox.clear()
    notify.sent.clear()
    return d


@pytest.fixture
def make_agent(db):
    def _make(*responses):
        llm = FakeLLM(*responses)
        return Agent(db, llm), llm
    return _make
