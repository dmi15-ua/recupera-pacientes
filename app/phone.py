"""Forma única para los teléfonos: E.164 con '+' (+34600112233).

La centralita, Twilio y WhatsApp escriben el mismo número de formas distintas.
Sin una forma canónica, el mismo paciente acabaría con varias conversaciones.
"""
from typing import Optional

DEFAULT_COUNTRY = "34"


def normalize(raw: Optional[str], country: str = DEFAULT_COUNTRY) -> str:
    if not raw:
        return ""
    s = str(raw).strip()
    for prefix in ("whatsapp:", "tel:", "sip:"):
        if s.lower().startswith(prefix):
            s = s[len(prefix):]
    s = s.split("@")[0]
    digits = "".join(c for c in s if c.isdigit())
    if not digits:
        return ""
    if s.startswith("+"):
        return "+" + digits
    if s.startswith("00"):
        return "+" + digits[2:]
    # Número nacional español de 9 cifras (fijo o móvil).
    if country == "34" and len(digits) == 9 and digits[0] in "6789":
        return "+34" + digits
    # WhatsApp manda el número con prefijo de país y sin '+'.
    if len(digits) > 9:
        return "+" + digits
    return digits


def to_wa(phone: str) -> str:
    """WhatsApp Cloud API espera solo dígitos, con prefijo de país."""
    return normalize(phone).lstrip("+")


def is_spanish_landline(phone: str) -> bool:
    """Los fijos españoles (8xx/9xx) no suelen tener WhatsApp."""
    p = normalize(phone)
    return p.startswith("+34") and len(p) == 12 and p[3] in "89"


def is_reachable_number(phone: str) -> bool:
    """Descarta números ocultos, cortos o especiales (no se les puede escribir)."""
    p = normalize(phone)
    return p.startswith("+") and 10 <= len(p) <= 16
