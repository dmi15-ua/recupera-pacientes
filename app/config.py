"""Configuración leída del entorno.

Todo tiene un valor por defecto que funciona en local sin credenciales: sin
WA_TOKEN los WhatsApp se imprimen en consola, sin GEMINI_API_KEY el agente
contesta con un texto fijo. Así se puede probar el flujo entero gratis.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _int(nombre: str, defecto: int) -> int:
    return int(os.getenv(nombre, str(defecto)))


def _bool(nombre: str, defecto: bool) -> bool:
    return os.getenv(nombre, "1" if defecto else "0").strip().lower() in ("1", "true", "si", "yes")


@dataclass
class Settings:
    database_url: str
    db_schema: str
    database_path: str
    clinics_file: str
    public_base_url: str
    trust_proxy: bool

    # WhatsApp Cloud API (Meta)
    wa_token: str
    wa_app_secret: str
    wa_verify_token: str
    wa_graph_version: str

    # LLM
    gemini_api_key: str
    gemini_model: str

    # Telefonía
    twilio_auth_token: str
    call_webhook_token: str

    # Avisos
    telegram_bot_token: str
    owner_telegram_chat_id: str

    # Panel de recepción y administración
    admin_token: str

    # Reglas de negocio
    missed_call_delay_s: int
    collapse_window_s: int
    recent_conversation_s: int
    debounce_s: int
    human_takeover_s: int
    idle_close_s: int
    retention_days: int
    max_llm_calls_per_day: int
    history_messages: int
    transcribe_audio: bool

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            # Supabase: Project Settings -> Database -> Connection string (URI).
            database_url=os.getenv("DATABASE_URL", ""),
            db_schema=os.getenv("DB_SCHEMA", "rp"),
            database_path=os.getenv("DATABASE_PATH", "data/app.db"),
            clinics_file=os.getenv("CLINICS_FILE", "clinicas.json"),
            public_base_url=os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/"),
            trust_proxy=_bool("TRUST_PROXY", True),
            wa_token=os.getenv("WA_TOKEN", ""),
            wa_app_secret=os.getenv("WA_APP_SECRET", ""),
            wa_verify_token=os.getenv("WA_VERIFY_TOKEN", ""),
            wa_graph_version=os.getenv("WA_GRAPH_VERSION", "v23.0"),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
            call_webhook_token=os.getenv("CALL_WEBHOOK_TOKEN", ""),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            owner_telegram_chat_id=os.getenv("OWNER_TELEGRAM_CHAT_ID", ""),
            admin_token=os.getenv("ADMIN_TOKEN", ""),
            # Se espera antes de escribir: si el paciente vuelve a llamar y le
            # cogen, o recepción le devuelve la llamada, no se manda nada.
            missed_call_delay_s=_int("MISSED_CALL_DELAY_S", 120),
            # Varias llamadas del mismo número en esta ventana = un solo mensaje.
            collapse_window_s=_int("COLLAPSE_WINDOW_S", 1800),
            # Si ya hablamos con este número hace poco, no se manda otro saludo.
            recent_conversation_s=_int("RECENT_CONVERSATION_S", 6 * 3600),
            # Se espera a que el paciente termine de escribir antes de responder.
            debounce_s=_int("DEBOUNCE_S", 6),
            # Cuando recepción escribe, el bot calla durante este tiempo.
            human_takeover_s=_int("HUMAN_TAKEOVER_S", 12 * 3600),
            idle_close_s=_int("IDLE_CLOSE_S", 3 * 24 * 3600),
            retention_days=_int("RETENTION_DAYS", 180),
            # Tope de coste: llamadas al LLM por conversación y día.
            max_llm_calls_per_day=_int("MAX_LLM_CALLS_PER_DAY", 20),
            history_messages=_int("HISTORY_MESSAGES", 16),
            transcribe_audio=_bool("TRANSCRIBE_AUDIO", True),
        )


settings = Settings.from_env()
