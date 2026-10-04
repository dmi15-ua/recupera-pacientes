"""Filtros deterministas antes de llamar al LLM.

Las urgencias vitales y las bajas no se dejan al criterio del modelo: se
detectan con reglas, se responde con un texto fijo y no se gasta ni un token.
"""
import re
import unicodedata


def _plain(text: str) -> str:
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


# Señales de alarma: se manda al 112 y se avisa a recepción. Mejor un falso
# positivo (el paciente recibe un consejo prudente) que un falso negativo.
RED_FLAGS = [
    r"no puedo respirar", r"(me )?cuesta (mucho )?respirar", r"me ahogo", r"dificultad (para|al) respirar",
    r"dolor (fuerte |muy fuerte )?(en el|de) pecho", r"infarto", r"ictus",
    r"(perdid[oa]|perder) (el )?conocimiento", r"inconsciente", r"desmay", r"convulsi",
    r"no (para|deja) de sangrar", r"sangra(ndo)? (mucho|sin parar)", r"hemorragia",
    r"(se me )?(esta )?hinchando (la cara|el cuello|la garganta|el ojo)",
    r"hinchazon (en|de) (la cara|el cuello|la garganta|el ojo)", r"(me )?cuesta tragar",
    r"anafila", r"reaccion alergica",
    r"suicid", r"quitarme la vida", r"me quiero morir", r"no quiero vivir",
]
_RED = re.compile("|".join(RED_FLAGS))

_OPTOUT_EXACT = {"baja", "stop", "darme de baja", "de baja", "unsubscribe"}
_OPTOUT = re.compile(
    r"(no me (escribais|escribas|escriban|mandeis|mandes|envieis) mas|"
    r"no quiero (recibir|mas) mensajes|dejad de escribir|dejen de escribir|darme de baja|"
    r"quiero la baja|borrad mi numero|borren mi numero)"
)

EMERGENCY_REPLY = (
    "Lo que describes puede ser una urgencia. Por favor, llama ahora al 112 "
    "o acude a urgencias. He avisado al equipo de la clínica para que te "
    "contacte lo antes posible."
)


def is_red_flag(text: str) -> bool:
    return bool(_RED.search(_plain(text)))


def is_optout(text: str) -> bool:
    t = _plain(text).strip(" .!¡")
    return t in _OPTOUT_EXACT or bool(_OPTOUT.search(t))
