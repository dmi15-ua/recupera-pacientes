"""Almacenamiento en SQLite.

SQLite basta de sobra para una clínica (o cien): cero coste, cero servidor y un
solo fichero que se copia para hacer backup. La app corre en un solo proceso,
así que un lock alrededor de la conexión es suficiente.

Todas las fechas son segundos epoch (UTC) en enteros.
"""
import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS clinics (
    id                  TEXT PRIMARY KEY,
    wa_phone_number_id  TEXT,
    data                TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_clinics_wa ON clinics(wa_phone_number_id)
    WHERE wa_phone_number_id IS NOT NULL AND wa_phone_number_id != '';

-- Números a los que llaman los pacientes -> clínica. Así se sabe de qué
-- clínica es cada llamada perdida sin fijar ningún id en la centralita.
CREATE TABLE IF NOT EXISTS clinic_numbers (
    number     TEXT PRIMARY KEY,
    clinic_id  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    clinic_id        TEXT NOT NULL,
    phone            TEXT NOT NULL,
    name             TEXT,
    mode             TEXT NOT NULL DEFAULT 'bot',      -- bot | human
    status           TEXT NOT NULL DEFAULT 'abierta',  -- abierta | cita_solicitada | requiere_humano | urgencia
    open             INTEGER NOT NULL DEFAULT 1,
    origin           TEXT NOT NULL,
    created_at       INTEGER NOT NULL,
    updated_at       INTEGER NOT NULL,
    last_patient_at  INTEGER,
    reply_due_at     INTEGER,
    human_until      INTEGER,
    llm_day          TEXT,
    llm_calls        INTEGER NOT NULL DEFAULT 0
);
-- Una sola conversación abierta por paciente y clínica, también con eventos
-- simultáneos: el INSERT duplicado falla y se reutiliza la existente.
CREATE UNIQUE INDEX IF NOT EXISTS idx_conv_open
    ON conversations(clinic_id, phone) WHERE open = 1;
CREATE INDEX IF NOT EXISTS idx_conv_due ON conversations(reply_due_at) WHERE reply_due_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL,   -- patient | bot | staff | system
    content          TEXT NOT NULL,
    wa_id            TEXT UNIQUE,     -- id de WhatsApp: evita procesar dos veces un reintento
    created_at       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS missed_calls (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    clinic_id        TEXT NOT NULL,
    phone            TEXT NOT NULL,
    call_ref         TEXT NOT NULL,
    received_at      INTEGER NOT NULL,
    send_after       INTEGER NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pendiente', -- pendiente | enviado | omitido | fallido
    reason           TEXT,
    wa_id            TEXT,
    UNIQUE (clinic_id, call_ref)
);
CREATE INDEX IF NOT EXISTS idx_missed_due ON missed_calls(status, send_after);

CREATE TABLE IF NOT EXISTS optouts (
    clinic_id   TEXT NOT NULL,
    phone       TEXT NOT NULL,
    created_at  INTEGER NOT NULL,
    PRIMARY KEY (clinic_id, phone)
);

-- Lo que el agente deja para recepción: citas pedidas, urgencias, dudas.
CREATE TABLE IF NOT EXISTS requests (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    clinic_id        TEXT NOT NULL,
    conversation_id  INTEGER NOT NULL,
    kind             TEXT NOT NULL,   -- cita | humano | urgencia | llamar
    phone            TEXT NOT NULL,
    name             TEXT,
    detail           TEXT,
    preference       TEXT,
    done             INTEGER NOT NULL DEFAULT 0,
    created_at       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    clinic_name   TEXT NOT NULL,
    contact_name  TEXT,
    phone         TEXT NOT NULL,
    email         TEXT,
    message       TEXT,
    created_at    INTEGER NOT NULL
);
"""


def now() -> int:
    return int(time.time())


class Database:
    def __init__(self, path: str):
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.lock = threading.RLock()
        self.conn.executescript(SCHEMA)

    # ------------------------------------------------------------ utilidades
    def _all(self, sql: str, args=()) -> List[Dict[str, Any]]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def _one(self, sql: str, args=()) -> Optional[Dict[str, Any]]:
        with self.lock:
            r = self.conn.execute(sql, args).fetchone()
            return dict(r) if r else None

    def _exec(self, sql: str, args=()) -> sqlite3.Cursor:
        with self.lock:
            return self.conn.execute(sql, args)

    # --------------------------------------------------------------- clínicas
    def upsert_clinic(self, clinic: Dict[str, Any]) -> None:
        from app.phone import normalize

        with self.lock:
            self._exec(
                "INSERT INTO clinics(id, wa_phone_number_id, data) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET wa_phone_number_id=excluded.wa_phone_number_id, data=excluded.data",
                (clinic["id"], clinic.get("wa_phone_number_id") or None, json.dumps(clinic, ensure_ascii=False)),
            )
            self._exec("DELETE FROM clinic_numbers WHERE clinic_id = ?", (clinic["id"],))
            for n in clinic.get("numeros_llamada", []):
                self._exec(
                    "INSERT OR REPLACE INTO clinic_numbers(number, clinic_id) VALUES (?, ?)",
                    (normalize(n), clinic["id"]),
                )

    def _clinic(self, row) -> Optional[Dict[str, Any]]:
        return json.loads(row["data"]) if row else None

    def get_clinic(self, clinic_id: str) -> Optional[Dict[str, Any]]:
        return self._clinic(self._one("SELECT data FROM clinics WHERE id = ?", (clinic_id,)))

    def clinic_by_wa_number(self, phone_number_id: str) -> Optional[Dict[str, Any]]:
        return self._clinic(self._one("SELECT data FROM clinics WHERE wa_phone_number_id = ?", (phone_number_id,)))

    def clinic_by_called_number(self, number: str) -> Optional[Dict[str, Any]]:
        row = self._one("SELECT clinic_id FROM clinic_numbers WHERE number = ?", (number,))
        return self.get_clinic(row["clinic_id"]) if row else None

    def list_clinics(self) -> List[Dict[str, Any]]:
        return [json.loads(r["data"]) for r in self._all("SELECT data FROM clinics")]

    # ------------------------------------------------------------ conversaciones
    def open_conversation(self, clinic_id: str, phone: str) -> Optional[Dict[str, Any]]:
        return self._one(
            "SELECT * FROM conversations WHERE clinic_id = ? AND phone = ? AND open = 1",
            (clinic_id, phone),
        )

    def get_or_open_conversation(self, clinic_id: str, phone: str, origin: str,
                                 name: Optional[str] = None) -> Dict[str, Any]:
        with self.lock:
            conv = self.open_conversation(clinic_id, phone)
            if conv:
                if name and not conv.get("name"):
                    self._exec("UPDATE conversations SET name = ? WHERE id = ?", (name, conv["id"]))
                    conv["name"] = name
                return conv
            t = now()
            cur = self._exec(
                "INSERT INTO conversations(clinic_id, phone, name, origin, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (clinic_id, phone, name, origin, t, t),
            )
            return self.get_conversation(cur.lastrowid)

    def get_conversation(self, conv_id: int) -> Optional[Dict[str, Any]]:
        return self._one("SELECT * FROM conversations WHERE id = ?", (conv_id,))

    def last_conversation(self, clinic_id: str, phone: str) -> Optional[Dict[str, Any]]:
        return self._one(
            "SELECT * FROM conversations WHERE clinic_id = ? AND phone = ? ORDER BY updated_at DESC LIMIT 1",
            (clinic_id, phone),
        )

    def update_conversation(self, conv_id: int, **campos) -> None:
        if not campos:
            return
        campos["updated_at"] = now()
        sets = ", ".join(f"{k} = ?" for k in campos)
        self._exec(f"UPDATE conversations SET {sets} WHERE id = ?", (*campos.values(), conv_id))

    def due_conversations(self, t: int) -> List[Dict[str, Any]]:
        return self._all(
            "SELECT * FROM conversations WHERE reply_due_at IS NOT NULL AND reply_due_at <= ? AND open = 1",
            (t,),
        )

    def list_conversations(self, clinic_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        return self._all(
            "SELECT c.*, (SELECT content FROM messages m WHERE m.conversation_id = c.id "
            "ORDER BY m.id DESC LIMIT 1) AS last_message "
            "FROM conversations c WHERE clinic_id = ? ORDER BY open DESC, updated_at DESC LIMIT ?",
            (clinic_id, limit),
        )

    def close_idle(self, older_than: int) -> int:
        cur = self._exec(
            "UPDATE conversations SET open = 0, reply_due_at = NULL WHERE open = 1 AND updated_at < ?",
            (older_than,),
        )
        return cur.rowcount

    def count_llm_call(self, conv_id: int, day: str) -> int:
        """Suma una llamada al LLM en el día y devuelve el total del día."""
        with self.lock:
            conv = self.get_conversation(conv_id)
            calls = (conv["llm_calls"] if conv["llm_day"] == day else 0) + 1
            self._exec("UPDATE conversations SET llm_day = ?, llm_calls = ? WHERE id = ?", (day, calls, conv_id))
            return calls

    # --------------------------------------------------------------- mensajes
    def add_message(self, conv_id: int, role: str, content: str, wa_id: Optional[str] = None) -> bool:
        """Guarda un mensaje. Devuelve False si ese wa_id ya estaba (reintento de Meta)."""
        try:
            self._exec(
                "INSERT INTO messages(conversation_id, role, content, wa_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (conv_id, role, content, wa_id, now()),
            )
        except sqlite3.IntegrityError:
            return False
        self._exec("UPDATE conversations SET updated_at = ? WHERE id = ?", (now(), conv_id))
        return True

    def message_seen(self, wa_id: str) -> bool:
        return self._one("SELECT 1 FROM messages WHERE wa_id = ?", (wa_id,)) is not None

    def history(self, conv_id: int, limit: int) -> List[Dict[str, Any]]:
        rows = self._all(
            "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
            (conv_id, limit),
        )
        return list(reversed(rows))

    def purge_old_messages(self, older_than: int) -> int:
        cur = self._exec(
            "DELETE FROM conversations WHERE open = 0 AND updated_at < ?", (older_than,)
        )
        return cur.rowcount

    # ---------------------------------------------------------- llamadas perdidas
    def add_missed_call(self, clinic_id: str, phone: str, call_ref: str, send_after: int) -> Optional[int]:
        """Registra la llamada. None si ya estaba (la centralita reintentó)."""
        try:
            cur = self._exec(
                "INSERT INTO missed_calls(clinic_id, phone, call_ref, received_at, send_after) VALUES (?, ?, ?, ?, ?)",
                (clinic_id, phone, call_ref, now(), send_after),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def pending_missed_for(self, clinic_id: str, phone: str, exclude_id: int) -> Optional[Dict[str, Any]]:
        return self._one(
            "SELECT * FROM missed_calls WHERE clinic_id = ? AND phone = ? AND status = 'pendiente' AND id != ?",
            (clinic_id, phone, exclude_id),
        )

    def recent_sent_missed(self, clinic_id: str, phone: str, since: int) -> Optional[Dict[str, Any]]:
        return self._one(
            "SELECT * FROM missed_calls WHERE clinic_id = ? AND phone = ? AND status = 'enviado' AND received_at >= ?",
            (clinic_id, phone, since),
        )

    def due_missed_calls(self, t: int) -> List[Dict[str, Any]]:
        return self._all(
            "SELECT * FROM missed_calls WHERE status = 'pendiente' AND send_after <= ? ORDER BY id", (t,)
        )

    def set_missed_status(self, call_id: int, status: str, reason: str = "", wa_id: Optional[str] = None,
                          send_after: Optional[int] = None) -> None:
        if send_after is not None:
            self._exec("UPDATE missed_calls SET send_after = ? WHERE id = ?", (send_after, call_id))
            return
        self._exec(
            "UPDATE missed_calls SET status = ?, reason = ?, wa_id = COALESCE(?, wa_id) WHERE id = ?",
            (status, reason, wa_id, call_id),
        )

    def cancel_pending_missed(self, clinic_id: str, phone: str, reason: str) -> int:
        cur = self._exec(
            "UPDATE missed_calls SET status = 'omitido', reason = ? "
            "WHERE clinic_id = ? AND phone = ? AND status = 'pendiente'",
            (reason, clinic_id, phone),
        )
        return cur.rowcount

    def missed_by_wa_id(self, wa_id: str) -> Optional[Dict[str, Any]]:
        return self._one("SELECT * FROM missed_calls WHERE wa_id = ?", (wa_id,))

    # ------------------------------------------------------------------ bajas
    def add_optout(self, clinic_id: str, phone: str) -> None:
        self._exec("INSERT OR IGNORE INTO optouts(clinic_id, phone, created_at) VALUES (?, ?, ?)",
                   (clinic_id, phone, now()))

    def is_opted_out(self, clinic_id: str, phone: str) -> bool:
        return self._one("SELECT 1 FROM optouts WHERE clinic_id = ? AND phone = ?", (clinic_id, phone)) is not None

    # -------------------------------------------------------------- solicitudes
    def add_request(self, clinic_id: str, conv_id: int, kind: str, phone: str, name: Optional[str] = None,
                    detail: Optional[str] = None, preference: Optional[str] = None) -> int:
        cur = self._exec(
            "INSERT INTO requests(clinic_id, conversation_id, kind, phone, name, detail, preference, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (clinic_id, conv_id, kind, phone, name, detail, preference, now()),
        )
        return cur.lastrowid

    def list_requests(self, clinic_id: str, only_open: bool = True) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM requests WHERE clinic_id = ?"
        if only_open:
            sql += " AND done = 0"
        return self._all(sql + " ORDER BY id DESC LIMIT 200", (clinic_id,))

    def close_request(self, clinic_id: str, req_id: int) -> None:
        self._exec("UPDATE requests SET done = 1 WHERE id = ? AND clinic_id = ?", (req_id, clinic_id))

    # ------------------------------------------------------------------ leads
    def add_lead(self, clinic_name: str, contact_name: Optional[str], phone: str,
                 email: Optional[str], message: Optional[str]) -> int:
        cur = self._exec(
            "INSERT INTO leads(clinic_name, contact_name, phone, email, message, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (clinic_name, contact_name, phone, email, message, now()),
        )
        return cur.lastrowid

    def recent_lead(self, phone: str, since: int) -> bool:
        return self._one("SELECT 1 FROM leads WHERE phone = ? AND created_at >= ?", (phone, since)) is not None
