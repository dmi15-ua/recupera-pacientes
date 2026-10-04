"""Almacenamiento: Supabase (Postgres) en producción, SQLite en local y tests.

Con DATABASE_URL=postgresql://... se usa Postgres. Las tablas van en un schema
propio (DB_SCHEMA, por defecto `rp`), para no mezclarse con lo que ya tengas en `public` y para que la
API REST de Supabase no las exponga (solo expone `public` por defecto).

Sin DATABASE_URL se usa un fichero SQLite (DATABASE_PATH): sirve para
desarrollar y para los tests sin depender de nada externo.

Las consultas se escriben una sola vez: `{T}` es el prefijo de tabla y `?` el
parámetro; cada motor los traduce a lo suyo. Las fechas son segundos epoch.
"""
import json
import os
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

CLINIC_JSON_FIELDS = ("numeros_llamada", "horario", "plantilla", "bloqueados")
CLINIC_FIELDS = (
    "id", "nombre", "asistente", "activa", "zona_horaria", "wa_phone_number_id",
    "telefono_recepcion", "segundos_espera", "numeros_llamada", "horario", "envio_permitido",
    "plantilla", "informacion", "instrucciones", "mensaje_voz", "telegram_chat_id",
    "panel_token", "bloqueados", "application_id", "wa_token",
)
# Columnas añadidas después de crear la tabla: se añaden solas al arrancar.
MIGRATIONS = (
    ("clinics", "wa_token", "TEXT"),
)
APPLICATION_JSON_FIELDS = ("horario", "servicios", "faq")

TABLES = """
CREATE TABLE IF NOT EXISTS {T}clinics (
    id                  TEXT PRIMARY KEY,
    nombre              TEXT NOT NULL,
    asistente           TEXT,
    activa              BOOLEAN NOT NULL DEFAULT TRUE,
    zona_horaria        TEXT NOT NULL DEFAULT 'Europe/Madrid',
    wa_phone_number_id  TEXT,
    telefono_recepcion  TEXT,
    segundos_espera     INTEGER DEFAULT 20,
    numeros_llamada     {JSON},
    horario             {JSON},
    envio_permitido     TEXT DEFAULT '09:00-21:00',
    plantilla           {JSON},
    informacion         TEXT,
    instrucciones       TEXT,
    mensaje_voz         TEXT,
    telegram_chat_id    TEXT,
    wa_token            TEXT,
    panel_token         TEXT,
    bloqueados          {JSON},
    application_id      BIGINT,
    created_at          BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS {T}conversations (
    id               {ID},
    clinic_id        TEXT NOT NULL,
    phone            TEXT NOT NULL,
    name             TEXT,
    mode             TEXT NOT NULL DEFAULT 'bot',
    status           TEXT NOT NULL DEFAULT 'abierta',
    open             INTEGER NOT NULL DEFAULT 1,
    origin           TEXT NOT NULL,
    created_at       BIGINT NOT NULL,
    updated_at       BIGINT NOT NULL,
    last_patient_at  BIGINT,
    reply_due_at     BIGINT,
    human_until      BIGINT,
    llm_day          TEXT,
    llm_calls        INTEGER NOT NULL DEFAULT 0
);
-- Una sola conversación abierta por paciente y clínica, también con eventos
-- simultáneos: el INSERT duplicado falla y se reutiliza la existente.
CREATE UNIQUE INDEX IF NOT EXISTS idx_conv_open ON {T}conversations(clinic_id, phone) WHERE open = 1;
CREATE INDEX IF NOT EXISTS idx_conv_due ON {T}conversations(reply_due_at) WHERE reply_due_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS {T}messages (
    id               {ID},
    conversation_id  BIGINT NOT NULL REFERENCES {T}conversations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL,
    content          TEXT NOT NULL,
    wa_id            TEXT UNIQUE,
    created_at       BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON {T}messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS {T}missed_calls (
    id           {ID},
    clinic_id    TEXT NOT NULL,
    phone        TEXT NOT NULL,
    call_ref     TEXT NOT NULL,
    received_at  BIGINT NOT NULL,
    send_after   BIGINT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pendiente',
    reason       TEXT,
    wa_id        TEXT,
    UNIQUE (clinic_id, call_ref)
);
CREATE INDEX IF NOT EXISTS idx_missed_due ON {T}missed_calls(status, send_after);

CREATE TABLE IF NOT EXISTS {T}optouts (
    clinic_id   TEXT NOT NULL,
    phone       TEXT NOT NULL,
    created_at  BIGINT NOT NULL,
    PRIMARY KEY (clinic_id, phone)
);

CREATE TABLE IF NOT EXISTS {T}requests (
    id               {ID},
    clinic_id        TEXT NOT NULL,
    conversation_id  BIGINT NOT NULL,
    kind             TEXT NOT NULL,
    phone            TEXT NOT NULL,
    name             TEXT,
    detail           TEXT,
    preference       TEXT,
    done             INTEGER NOT NULL DEFAULT 0,
    created_at       BIGINT NOT NULL
);

-- Formulario corto de la landing: alguien quiere que le llamemos.
CREATE TABLE IF NOT EXISTS {T}leads (
    id            {ID},
    clinic_name   TEXT NOT NULL,
    contact_name  TEXT,
    phone         TEXT NOT NULL,
    email         TEXT,
    message       TEXT,
    status        TEXT NOT NULL DEFAULT 'nuevo',
    created_at    BIGINT NOT NULL
);

-- Ficha de alta: servicios, precios, horario y preguntas frecuentes.
-- Es lo que el asistente necesita para no inventarse nada.
CREATE TABLE IF NOT EXISTS {T}clinic_applications (
    id                  {ID},
    status              TEXT NOT NULL DEFAULT 'nueva',
    clinic_name         TEXT NOT NULL,
    contact_name        TEXT,
    email               TEXT,
    phone               TEXT NOT NULL,
    especialidad        TEXT,
    direccion           TEXT,
    web                 TEXT,
    horario             {JSON},
    servicios           {JSON},
    faq                 {JSON},
    instrucciones       TEXT,
    prohibiciones       TEXT,
    asistente           TEXT,
    telefono_clinica    TEXT,
    whatsapp_number     TEXT,
    centralita          TEXT,
    clinic_id           TEXT,
    created_at          BIGINT NOT NULL
);
"""

PG_EXTRA = """
ALTER TABLE {T}clinics ENABLE ROW LEVEL SECURITY;
ALTER TABLE {T}conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE {T}messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE {T}missed_calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE {T}optouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE {T}requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE {T}leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE {T}clinic_applications ENABLE ROW LEVEL SECURITY;
"""


def now() -> int:
    return int(time.time())


def slugify(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40] or "clinica"


class Database:
    def __init__(self, url: str, schema: str = "rp"):
        self.pg = url.startswith(("postgres://", "postgresql://"))
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
            raise ValueError("Nombre de schema no válido")
        self.lock = threading.RLock()
        if self.pg:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            self.IntegrityError = psycopg.errors.IntegrityError
            # prepare_threshold=None: el pooler de Supabase en modo transacción
            # no admite sentencias preparadas.
            self.pool = ConnectionPool(
                url, min_size=1, max_size=5, open=True,
                kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": None},
            )
            self.prefix = schema + "."
            ddl = f"CREATE SCHEMA IF NOT EXISTS {schema};\n" + TABLES + PG_EXTRA
            ddl = ddl.replace("{ID}", "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY").replace("{JSON}", "JSONB")
        else:
            if url != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(url)), exist_ok=True)
            self.IntegrityError = sqlite3.IntegrityError
            self.conn = sqlite3.connect(url, check_same_thread=False, isolation_level=None)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.prefix = ""
            ddl = TABLES.replace("{ID}", "INTEGER PRIMARY KEY AUTOINCREMENT").replace("{JSON}", "TEXT")
        for stmt in ddl.replace("{T}", self.prefix).split(";"):
            if stmt.strip():
                self._run(stmt, ())
        for table, column, sql_type in MIGRATIONS:
            if not self._has_column(table, column):
                self._run(f"ALTER TABLE {{T}}{table} ADD COLUMN {column} {sql_type}")

    def _has_column(self, table: str, column: str) -> bool:
        if self.pg:
            return self._one("SELECT 1 AS x FROM information_schema.columns "
                             "WHERE table_schema = ? AND table_name = ? AND column_name = ?",
                             (self.prefix.rstrip("."), table, column)) is not None
        return any(r["name"] == column for r in self._all(f"PRAGMA table_info({table})"))

    # ------------------------------------------------------------ utilidades
    def _sql(self, sql: str) -> str:
        sql = sql.replace("{T}", self.prefix)
        return sql.replace("?", "%s") if self.pg else sql

    def _run(self, sql: str, args=(), fetch: str = "none"):
        sql = self._sql(sql)
        if self.pg:
            with self.pool.connection() as conn:
                cur = conn.execute(sql, args)
                if fetch == "all":
                    return cur.fetchall()
                if fetch == "one":
                    return cur.fetchone()
                return cur.rowcount
        with self.lock:
            cur = self.conn.execute(sql, args)
            if fetch == "all":
                return [dict(r) for r in cur.fetchall()]
            if fetch == "one":
                # fetchall: con RETURNING, SQLite no termina la sentencia hasta
                # leer todas las filas.
                rows = cur.fetchall()
                return dict(rows[0]) if rows else None
            return cur.rowcount

    def _all(self, sql: str, args=()) -> List[Dict[str, Any]]:
        return self._run(sql, args, "all")

    def _one(self, sql: str, args=()) -> Optional[Dict[str, Any]]:
        return self._run(sql, args, "one")

    def _exec(self, sql: str, args=()) -> int:
        return self._run(sql, args)

    def _insert(self, sql: str, args=()) -> int:
        return self._run(sql + " RETURNING id", args, "one")["id"]

    def _json_in(self, value):
        if value is None:
            return None
        if self.pg:
            from psycopg.types.json import Jsonb
            return Jsonb(value)
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _json_out(row: Optional[Dict[str, Any]], fields) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        for f in fields:
            if isinstance(row.get(f), str):
                try:
                    row[f] = json.loads(row[f])
                except ValueError:
                    row[f] = None
        return row

    # --------------------------------------------------------------- clínicas
    def _clinic(self, row) -> Optional[Dict[str, Any]]:
        c = self._json_out(row, CLINIC_JSON_FIELDS)
        if c is not None:
            c["activa"] = bool(c.get("activa"))
            for f in ("numeros_llamada", "bloqueados"):
                c[f] = c.get(f) or []
            c["horario"] = c.get("horario") or {}
            c["plantilla"] = c.get("plantilla") or {}
            c = {k: v for k, v in c.items() if v is not None}
        return c

    def upsert_clinic(self, clinic: Dict[str, Any], overwrite: bool = True) -> None:
        fields = [f for f in CLINIC_FIELDS if f in clinic]
        values = [self._json_in(clinic[f]) if f in CLINIC_JSON_FIELDS else clinic[f] for f in fields]
        cols = ", ".join(fields + ["created_at"])
        marks = ", ".join("?" for _ in range(len(fields) + 1))
        if overwrite:
            updates = ", ".join(f"{f} = excluded.{f}" for f in fields if f != "id")
            conflict = f"ON CONFLICT (id) DO UPDATE SET {updates}"
        else:
            conflict = "ON CONFLICT (id) DO NOTHING"
        self._exec(f"INSERT INTO {{T}}clinics ({cols}) VALUES ({marks}) {conflict}", (*values, now()))

    def get_clinic(self, clinic_id: str) -> Optional[Dict[str, Any]]:
        return self._clinic(self._one("SELECT * FROM {T}clinics WHERE id = ?", (clinic_id,)))

    def clinic_by_wa_number(self, phone_number_id: str) -> Optional[Dict[str, Any]]:
        return self._clinic(self._one("SELECT * FROM {T}clinics WHERE wa_phone_number_id = ?", (phone_number_id,)))

    def list_clinics(self) -> List[Dict[str, Any]]:
        return [self._clinic(r) for r in self._all("SELECT * FROM {T}clinics ORDER BY created_at")]

    def clinic_by_called_number(self, number: str) -> Optional[Dict[str, Any]]:
        # Pocas clínicas: se filtra en Python y la consulta vale igual para los
        # dos motores. Así, si editas los números en Supabase, se aplica al momento.
        from app.phone import normalize
        for c in self.list_clinics():
            if number in {normalize(n) for n in c.get("numeros_llamada", [])}:
                return c
        return None

    def set_clinic_active(self, clinic_id: str, active: bool) -> None:
        self._exec("UPDATE {T}clinics SET activa = ? WHERE id = ?", (active, clinic_id))

    def clinic_stats(self, clinic_id: str, since: int) -> Dict[str, int]:
        def count(sql):
            return self._one(sql, (clinic_id, since))["n"]
        return {
            "llamadas_perdidas": count("SELECT COUNT(*) AS n FROM {T}missed_calls WHERE clinic_id = ? AND received_at >= ?"),
            "whatsapps_enviados": count("SELECT COUNT(*) AS n FROM {T}missed_calls WHERE clinic_id = ? "
                                        "AND status = 'enviado' AND received_at >= ?"),
            "conversaciones": count("SELECT COUNT(*) AS n FROM {T}conversations WHERE clinic_id = ? AND created_at >= ?"),
            "solicitudes_cita": count("SELECT COUNT(*) AS n FROM {T}requests WHERE clinic_id = ? "
                                      "AND kind = 'cita' AND created_at >= ?"),
        }

    # ------------------------------------------------------------ conversaciones
    def open_conversation(self, clinic_id: str, phone: str) -> Optional[Dict[str, Any]]:
        return self._one("SELECT * FROM {T}conversations WHERE clinic_id = ? AND phone = ? AND open = 1",
                         (clinic_id, phone))

    def get_or_open_conversation(self, clinic_id: str, phone: str, origin: str,
                                 name: Optional[str] = None) -> Dict[str, Any]:
        conv = self.open_conversation(clinic_id, phone)
        if not conv:
            t = now()
            try:
                new_id = self._insert(
                    "INSERT INTO {T}conversations (clinic_id, phone, name, origin, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)", (clinic_id, phone, name, origin, t, t))
                return self.get_conversation(new_id)
            except self.IntegrityError:
                # Otro evento la acaba de crear a la vez: se usa esa.
                conv = self.open_conversation(clinic_id, phone)
        if name and not conv.get("name"):
            self._exec("UPDATE {T}conversations SET name = ? WHERE id = ?", (name, conv["id"]))
            conv["name"] = name
        return conv

    def get_conversation(self, conv_id: int) -> Optional[Dict[str, Any]]:
        return self._one("SELECT * FROM {T}conversations WHERE id = ?", (conv_id,))

    def last_conversation(self, clinic_id: str, phone: str) -> Optional[Dict[str, Any]]:
        return self._one("SELECT * FROM {T}conversations WHERE clinic_id = ? AND phone = ? "
                         "ORDER BY updated_at DESC LIMIT 1", (clinic_id, phone))

    def update_conversation(self, conv_id: int, **campos) -> None:
        if not campos:
            return
        campos["updated_at"] = now()
        sets = ", ".join(f"{k} = ?" for k in campos)
        self._exec(f"UPDATE {{T}}conversations SET {sets} WHERE id = ?", (*campos.values(), conv_id))

    def due_conversations(self, t: int) -> List[Dict[str, Any]]:
        return self._all("SELECT * FROM {T}conversations WHERE reply_due_at IS NOT NULL "
                         "AND reply_due_at <= ? AND open = 1", (t,))

    def list_conversations(self, clinic_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        return self._all(
            "SELECT c.*, (SELECT content FROM {T}messages m WHERE m.conversation_id = c.id "
            "ORDER BY m.id DESC LIMIT 1) AS last_message "
            "FROM {T}conversations c WHERE clinic_id = ? ORDER BY open DESC, updated_at DESC LIMIT ?",
            (clinic_id, limit))

    def close_idle(self, older_than: int) -> int:
        return self._exec("UPDATE {T}conversations SET open = 0, reply_due_at = NULL "
                          "WHERE open = 1 AND updated_at < ?", (older_than,))

    def count_llm_call(self, conv_id: int, day: str) -> int:
        """Suma una llamada al LLM en el día y devuelve el total del día (atómico)."""
        row = self._one(
            "UPDATE {T}conversations SET llm_calls = CASE WHEN llm_day = ? THEN llm_calls + 1 ELSE 1 END, "
            "llm_day = ? WHERE id = ? RETURNING llm_calls", (day, day, conv_id))
        return row["llm_calls"]

    # --------------------------------------------------------------- mensajes
    def add_message(self, conv_id: int, role: str, content: str, wa_id: Optional[str] = None) -> bool:
        """Guarda un mensaje. Devuelve False si ese wa_id ya estaba (reintento de Meta)."""
        try:
            self._exec("INSERT INTO {T}messages (conversation_id, role, content, wa_id, created_at) "
                       "VALUES (?, ?, ?, ?, ?)", (conv_id, role, content, wa_id, now()))
        except self.IntegrityError:
            return False
        self._exec("UPDATE {T}conversations SET updated_at = ? WHERE id = ?", (now(), conv_id))
        return True

    def message_seen(self, wa_id: str) -> bool:
        return self._one("SELECT 1 AS x FROM {T}messages WHERE wa_id = ?", (wa_id,)) is not None

    def history(self, conv_id: int, limit: int) -> List[Dict[str, Any]]:
        rows = self._all("SELECT role, content, created_at FROM {T}messages WHERE conversation_id = ? "
                         "ORDER BY id DESC LIMIT ?", (conv_id, limit))
        return list(reversed(rows))

    def purge_older_than(self, cutoff: int) -> int:
        n = self._exec("DELETE FROM {T}conversations WHERE open = 0 AND updated_at < ?", (cutoff,))
        self._exec("DELETE FROM {T}requests WHERE created_at < ?", (cutoff,))
        self._exec("DELETE FROM {T}missed_calls WHERE received_at < ?", (cutoff,))
        return n

    # ---------------------------------------------------------- llamadas perdidas
    def add_missed_call(self, clinic_id: str, phone: str, call_ref: str, send_after: int) -> Optional[int]:
        """Registra la llamada. None si ya estaba (la centralita reintentó)."""
        try:
            return self._insert("INSERT INTO {T}missed_calls (clinic_id, phone, call_ref, received_at, send_after) "
                                "VALUES (?, ?, ?, ?, ?)", (clinic_id, phone, call_ref, now(), send_after))
        except self.IntegrityError:
            return None

    def recent_sent_missed(self, clinic_id: str, phone: str, since: int) -> Optional[Dict[str, Any]]:
        return self._one("SELECT * FROM {T}missed_calls WHERE clinic_id = ? AND phone = ? "
                         "AND status = 'enviado' AND received_at >= ?", (clinic_id, phone, since))

    def due_missed_calls(self, t: int) -> List[Dict[str, Any]]:
        return self._all("SELECT * FROM {T}missed_calls WHERE status = 'pendiente' AND send_after <= ? ORDER BY id",
                         (t,))

    def set_missed_status(self, call_id: int, status: str, reason: str = "", wa_id: Optional[str] = None,
                          send_after: Optional[int] = None) -> None:
        if send_after is not None:
            self._exec("UPDATE {T}missed_calls SET send_after = ? WHERE id = ?", (send_after, call_id))
            return
        self._exec("UPDATE {T}missed_calls SET status = ?, reason = ?, wa_id = COALESCE(?, wa_id) WHERE id = ?",
                   (status, reason, wa_id, call_id))

    def cancel_pending_missed(self, clinic_id: str, phone: str, reason: str) -> int:
        return self._exec("UPDATE {T}missed_calls SET status = 'omitido', reason = ? "
                          "WHERE clinic_id = ? AND phone = ? AND status = 'pendiente'", (reason, clinic_id, phone))

    def missed_by_wa_id(self, wa_id: str) -> Optional[Dict[str, Any]]:
        return self._one("SELECT * FROM {T}missed_calls WHERE wa_id = ?", (wa_id,))

    # ------------------------------------------------------------------ bajas
    def add_optout(self, clinic_id: str, phone: str) -> None:
        self._exec("INSERT INTO {T}optouts (clinic_id, phone, created_at) VALUES (?, ?, ?) "
                   "ON CONFLICT DO NOTHING", (clinic_id, phone, now()))

    def is_opted_out(self, clinic_id: str, phone: str) -> bool:
        return self._one("SELECT 1 AS x FROM {T}optouts WHERE clinic_id = ? AND phone = ?",
                         (clinic_id, phone)) is not None

    # -------------------------------------------------------------- solicitudes
    def add_request(self, clinic_id: str, conv_id: int, kind: str, phone: str, name: Optional[str] = None,
                    detail: Optional[str] = None, preference: Optional[str] = None) -> int:
        return self._insert(
            "INSERT INTO {T}requests (clinic_id, conversation_id, kind, phone, name, detail, preference, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (clinic_id, conv_id, kind, phone, name, detail, preference, now()))

    def list_requests(self, clinic_id: str, only_open: bool = True) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM {T}requests WHERE clinic_id = ?"
        if only_open:
            sql += " AND done = 0"
        return self._all(sql + " ORDER BY id DESC LIMIT 200", (clinic_id,))

    def close_request(self, clinic_id: str, req_id: int) -> None:
        self._exec("UPDATE {T}requests SET done = 1 WHERE id = ? AND clinic_id = ?", (req_id, clinic_id))

    # ------------------------------------------------------------------ leads
    def add_lead(self, clinic_name: str, contact_name: Optional[str], phone: str,
                 email: Optional[str], message: Optional[str]) -> int:
        return self._insert("INSERT INTO {T}leads (clinic_name, contact_name, phone, email, message, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?)", (clinic_name, contact_name, phone, email, message, now()))

    def recent_lead(self, phone: str, since: int) -> bool:
        return self._one("SELECT 1 AS x FROM {T}leads WHERE phone = ? AND created_at >= ?",
                         (phone, since)) is not None

    def list_leads(self, limit: int = 200) -> List[Dict[str, Any]]:
        return self._all("SELECT * FROM {T}leads ORDER BY id DESC LIMIT ?", (limit,))

    def set_lead_status(self, lead_id: int, status: str) -> None:
        self._exec("UPDATE {T}leads SET status = ? WHERE id = ?", (status, lead_id))

    # ------------------------------------------------------- fichas de alta
    def add_application(self, data: Dict[str, Any]) -> int:
        fields = [k for k in data if k not in ("id", "status", "clinic_id", "created_at")]
        values = [self._json_in(data[f]) if f in APPLICATION_JSON_FIELDS else data[f] for f in fields]
        cols = ", ".join(fields + ["created_at"])
        marks = ", ".join("?" for _ in range(len(fields) + 1))
        return self._insert(f"INSERT INTO {{T}}clinic_applications ({cols}) VALUES ({marks})", (*values, now()))

    def get_application(self, app_id: int) -> Optional[Dict[str, Any]]:
        return self._json_out(self._one("SELECT * FROM {T}clinic_applications WHERE id = ?", (app_id,)),
                              APPLICATION_JSON_FIELDS)

    def list_applications(self, limit: int = 200) -> List[Dict[str, Any]]:
        return [self._json_out(r, APPLICATION_JSON_FIELDS)
                for r in self._all("SELECT * FROM {T}clinic_applications ORDER BY id DESC LIMIT ?", (limit,))]

    def recent_application(self, phone: str, since: int) -> bool:
        return self._one("SELECT 1 AS x FROM {T}clinic_applications WHERE phone = ? AND created_at >= ?",
                         (phone, since)) is not None

    def set_application_status(self, app_id: int, status: str, clinic_id: Optional[str] = None) -> None:
        self._exec("UPDATE {T}clinic_applications SET status = ?, clinic_id = COALESCE(?, clinic_id) WHERE id = ?",
                   (status, clinic_id, app_id))

    def unique_clinic_id(self, name: str) -> str:
        base = slugify(name)
        candidate, n = base, 2
        while self.get_clinic(candidate):
            candidate, n = f"{base}-{n}", n + 1
        return candidate
