"""Horarios de la clínica y franja en la que se permite escribir.

Formato en clinicas.json:
    "horario": {"lun": ["09:00-14:00", "16:00-20:00"], ..., "sab": ["10:00-14:00"]},
    "envio_permitido": "09:00-21:00"

Las cuentas se hacen siempre en la zona horaria de la clínica: el servidor
puede estar en UTC y un mensaje a las 3 de la madrugada sienta fatal.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

DAYS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def tz(clinic: Dict) -> ZoneInfo:
    return ZoneInfo(clinic.get("zona_horaria", "Europe/Madrid"))


def local(clinic: Dict, t: int) -> datetime:
    return datetime.fromtimestamp(t, tz(clinic))


def _parse_range(r: str) -> Tuple[int, int]:
    a, b = r.split("-")
    ha, ma = a.strip().split(":")
    hb, mb = b.strip().split(":")
    return int(ha) * 60 + int(ma), int(hb) * 60 + int(mb)


def _ranges_for(clinic: Dict, weekday: int) -> List[Tuple[int, int]]:
    return [_parse_range(r) for r in clinic.get("horario", {}).get(DAYS[weekday], [])]


def is_open(clinic: Dict, t: int) -> bool:
    d = local(clinic, t)
    minute = d.hour * 60 + d.minute
    return any(a <= minute < b for a, b in _ranges_for(clinic, d.weekday()))


def describe(clinic: Dict) -> str:
    lines = []
    for i, key in enumerate(DAYS):
        ranges = clinic.get("horario", {}).get(key, [])
        lines.append(f"{DAY_NAMES[i].capitalize()}: {', '.join(ranges) if ranges else 'cerrado'}")
    return "\n".join(lines)


def next_send_time(clinic: Dict, t: int) -> int:
    """Primer instante >= t dentro de la franja en la que se permite escribir."""
    start, end = _parse_range(clinic.get("envio_permitido", "09:00-21:00"))
    d = local(clinic, t)
    minute = d.hour * 60 + d.minute
    if start <= minute < end:
        return t
    day = d if minute < start else d + timedelta(days=1)
    target = day.replace(hour=start // 60, minute=start % 60, second=0, microsecond=0)
    return int(target.timestamp())


def now_text(clinic: Dict, t: int) -> str:
    d = local(clinic, t)
    return f"{DAY_NAMES[d.weekday()]} {d.day:02d}/{d.month:02d}/{d.year}, {d.hour:02d}:{d.minute:02d}"
