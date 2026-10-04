"""Ficha de alta de una clínica -> clínica lista para el asistente.

La ficha recoge los datos de forma estructurada (servicios con precio, horario
por día, preguntas frecuentes) y aquí se convierten en el texto que lee el
asistente. Cuanto más completa la ficha, menos veces tendrá que decir "lo
consulto con el equipo".
"""
import re
import secrets
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.hours import DAYS
from app.phone import normalize

FAQ_LABELS = {
    "primera_visita": "Primera visita",
    "pagos": "Formas de pago",
    "financiacion": "Financiación",
    "seguros": "Seguros y mutuas",
    "parking": "Aparcamiento y cómo llegar",
    "accesibilidad": "Accesibilidad",
    "idiomas": "Idiomas",
    "urgencias": "Urgencias",
    "otros": "Otros datos",
}

_RANGE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-4]):[0-5]\d$")


class Servicio(BaseModel):
    servicio: str = Field(..., min_length=1, max_length=120)
    precio: str = Field("", max_length=60)
    nota: str = Field("", max_length=200)


class ApplicationIn(BaseModel):
    clinica: str = Field(..., min_length=2, max_length=160)
    contacto: Optional[str] = Field(None, max_length=120)
    email: Optional[str] = Field(None, max_length=160)
    telefono: str = Field(..., min_length=6, max_length=30)
    telefono_clinica: Optional[str] = Field(None, max_length=30)
    whatsapp_number: Optional[str] = Field(None, max_length=30)
    especialidad: Optional[str] = Field(None, max_length=80)
    direccion: Optional[str] = Field(None, max_length=300)
    web: Optional[str] = Field(None, max_length=200)
    centralita: Optional[str] = Field(None, max_length=120)
    asistente: Optional[str] = Field(None, max_length=40)
    horario: Dict[str, List[str]] = Field(default_factory=dict)
    servicios: List[Servicio] = Field(..., min_length=1, max_length=80)
    faq: Dict[str, str] = Field(default_factory=dict)
    instrucciones: Optional[str] = Field(None, max_length=2000)
    prohibiciones: Optional[str] = Field(None, max_length=2000)
    acepta: bool = False
    hp: Optional[str] = Field(None, max_length=200)  # trampa para bots

    @field_validator("horario")
    @classmethod
    def _check_horario(cls, v: Dict[str, List[str]]) -> Dict[str, List[str]]:
        clean: Dict[str, List[str]] = {}
        for day, ranges in v.items():
            if day not in DAYS:
                raise ValueError(f"Día no válido: {day}")
            out = []
            for r in ranges[:4]:
                r = r.replace(" ", "").replace(".", ":")
                if not _RANGE.match(r):
                    raise ValueError(f"Horario no válido: {r} (usa 09:00-14:00)")
                out.append(r)
            clean[day] = out
        return clean

    @field_validator("faq")
    @classmethod
    def _check_faq(cls, v: Dict[str, str]) -> Dict[str, str]:
        return {k: s.strip()[:600] for k, s in v.items() if k in FAQ_LABELS and s and s.strip()}


def application_row(a: ApplicationIn) -> Dict[str, Any]:
    """Lo que se guarda en clinic_applications."""
    return {
        "clinic_name": a.clinica.strip(),
        "contact_name": a.contacto,
        "email": a.email,
        "phone": normalize(a.telefono),
        "telefono_clinica": normalize(a.telefono_clinica) if a.telefono_clinica else None,
        "whatsapp_number": normalize(a.whatsapp_number) if a.whatsapp_number else None,
        "especialidad": a.especialidad,
        "direccion": a.direccion,
        "web": a.web,
        "centralita": a.centralita,
        "asistente": a.asistente,
        "horario": a.horario,
        "servicios": [s.model_dump() for s in a.servicios],
        "faq": a.faq,
        "instrucciones": a.instrucciones,
        "prohibiciones": a.prohibiciones,
    }


def build_informacion(app: Dict[str, Any]) -> str:
    """Texto con todo lo que el asistente puede afirmar sobre la clínica."""
    lines: List[str] = []
    if app.get("especialidad"):
        lines.append(f"Especialidad: {app['especialidad']}")
    if app.get("direccion"):
        lines.append(f"Dirección: {app['direccion']}")
    if app.get("telefono_clinica"):
        lines.append(f"Teléfono: {app['telefono_clinica']}")
    if app.get("web"):
        lines.append(f"Web: {app['web']}")

    lines.append("\nServicios y precios:")
    for s in app.get("servicios") or []:
        line = f"- {s['servicio']}"
        if s.get("precio"):
            line += f": {s['precio']}"
        if s.get("nota"):
            line += f" ({s['nota']})"
        lines.append(line)

    faq = app.get("faq") or {}
    if faq:
        lines.append("\nOtros datos:")
        for key, label in FAQ_LABELS.items():
            if faq.get(key):
                lines.append(f"- {label}: {faq[key]}")
    # Lo que la clínica dejó en blanco se dice explícitamente: si no, el modelo
    # tiende a rellenar el hueco ("no tenemos parking").
    unknown = [label.lower() for key, label in FAQ_LABELS.items() if key != "otros" and not faq.get(key)]
    if unknown:
        lines.append("\nDatos que NO tienes (no los afirmes ni los niegues; ofrece consultarlo con el equipo): "
                     + ", ".join(unknown) + ".")
    return "\n".join(lines).strip()


def build_instrucciones(app: Dict[str, Any]) -> str:
    parts = []
    if app.get("instrucciones"):
        parts.append(app["instrucciones"].strip())
    if app.get("prohibiciones"):
        parts.append("NUNCA hables de lo siguiente (si preguntan, di que lo consulten con el equipo): "
                     + app["prohibiciones"].strip())
    return "\n".join(parts)


def clinic_from_application(app: Dict[str, Any], clinic_id: str) -> Dict[str, Any]:
    """Clínica INACTIVA: falta conectar WhatsApp antes de activarla."""
    phone = app.get("telefono_clinica")
    return {
        "id": clinic_id,
        "nombre": app["clinic_name"],
        "asistente": app.get("asistente") or "el asistente",
        "activa": False,
        "zona_horaria": "Europe/Madrid",
        "telefono_recepcion": phone,
        "numeros_llamada": [phone] if phone else [],
        "horario": app.get("horario") or {},
        "envio_permitido": "09:00-21:00",
        "plantilla": {"nombre": "llamada_perdida", "idioma": "es", "con_nombre_clinica": True},
        "informacion": build_informacion(app),
        "instrucciones": build_instrucciones(app),
        "panel_token": secrets.token_urlsafe(24),
        "bloqueados": [],
        "application_id": app["id"],
    }


def missing_config(clinic: Dict[str, Any]) -> List[str]:
    """Lo que falta para poder activar una clínica."""
    missing = []
    if not clinic.get("wa_phone_number_id"):
        missing.append("WhatsApp (wa_phone_number_id)")
    if not clinic.get("numeros_llamada"):
        missing.append("número al que llaman los pacientes")
    if not clinic.get("informacion"):
        missing.append("información de la clínica")
    if not clinic.get("horario"):
        missing.append("horario")
    return missing
