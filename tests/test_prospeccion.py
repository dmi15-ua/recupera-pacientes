"""Lógica de la skill de prospección (sin llamar a Google)."""
import importlib.util
import os
from datetime import datetime, timezone

RUTA = os.path.join(os.path.dirname(__file__), "..", ".claude", "skills", "prospeccion-clinicas",
                    "scripts", "google_places.py")
spec = importlib.util.spec_from_file_location("google_places", RUTA)
gp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gp)

AHORA = datetime(2026, 10, 8, tzinfo=timezone.utc)


def review(texto, fecha="2026-05-01T10:00:00Z", estrellas=1):
    return {"text": {"text": texto}, "publishTime": fecha, "rating": estrellas,
            "authorAttribution": {"displayName": "Persona Real"}}


def periodo(dia, ini, fin):
    return {"open": {"day": dia, "hour": ini[0], "minute": ini[1]}, "close": {"day": dia, "hour": fin[0], "minute": fin[1]}}


PARTIDO = {"periods": [p for d in (1, 2, 3, 4, 5) for p in (periodo(d, (9, 0), (14, 0)), periodo(d, (16, 30), (20, 0)))]}
CONTINUO = {"periods": [periodo(d, (9, 0), (20, 0)) for d in (1, 2, 3, 4, 5, 6)]}


def test_detecta_quejas_de_telefono_y_no_guarda_autor():
    q = gp.quejas_telefono([
        review("Imposible contactar, nunca cogen el teléfono"),
        review("Llamé varias veces y nadie contesta"),
        review("Muy buen trato, repetiré"),
    ], ahora=AHORA)
    assert len(q) == 2
    assert all(set(x) == {"fecha", "estrellas", "texto"} for x in q)  # sin nombre del autor


def test_ignora_quejas_antiguas():
    assert gp.quejas_telefono([review("no cogen el teléfono", fecha="2019-01-01T00:00:00Z")], ahora=AHORA) == []


def test_horario_partido_y_sin_sabado():
    h = gp.analizar_horario(PARTIDO)
    assert h["mediodia"] and h["sin_sabado"] and not h["cierra_pronto"]
    c = gp.analizar_horario(CONTINUO)
    assert not c["mediodia"] and not c["sin_sabado"]
    assert gp.analizar_horario(None)["conocido"] is False


def test_movil():
    assert gp.es_movil("612 34 56 78") and gp.es_movil("+34 678 499 634")
    assert not gp.es_movil("950 681 301") and not gp.es_movil("")


def lugar(nombre, **kw):
    base = {"displayName": {"text": nombre}, "businessStatus": "OPERATIONAL", "nationalPhoneNumber": "950 123 456",
            "userRatingCount": 40, "regularOpeningHours": CONTINUO, "types": ["dentist"]}
    base.update(kw)
    return base


def test_prioridades_y_exclusiones():
    alta = gp.evaluar(lugar("Dental Sol", reviews=[review("no cogen el teléfono nunca")]))
    media = gp.evaluar(lugar("Dental Luna", regularOpeningHours=PARTIDO))
    verificar = gp.evaluar(lugar("Dental Mar"))
    assert (alta["prioridad"], media["prioridad"], verificar["prioridad"]) == ("Alta", "Media", "Por verificar")
    assert alta["potencial"] > media["potencial"] > verificar["potencial"]
    assert gp.evaluar(lugar("Clínica Dental Sanitas Milenium")) is None
    assert gp.evaluar(lugar("Hospital Comarcal", types=["hospital"])) is None
    assert gp.evaluar(lugar("Dental Cerrada", businessStatus="CLOSED_PERMANENTLY")) is None


def test_sin_sabado_solo_cuenta_con_mucha_demanda():
    solo = gp.evaluar(lugar("Dental A", regularOpeningHours={"periods": [periodo(d, (9, 0), (20, 0)) for d in (1, 2, 3, 4, 5)]}))
    demanda = gp.evaluar(lugar("Dental B", userRatingCount=250,
                               regularOpeningHours={"periods": [periodo(d, (9, 0), (20, 0)) for d in (1, 2, 3, 4, 5)]}))
    assert solo["prioridad"] == "Por verificar" and demanda["prioridad"] == "Media"
