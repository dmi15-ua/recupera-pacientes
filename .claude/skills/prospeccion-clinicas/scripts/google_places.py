#!/usr/bin/env python3
"""Prospección de clínicas con la API oficial de Google Places (New).

Busca clínicas en una provincia, lee sus valoraciones de Google (la API devuelve
hasta 5 por clínica), detecta quejas por el teléfono, analiza el horario y
puntúa cada clínica. Solo usa la biblioteca estándar.

Uso:
  GOOGLE_PLACES_API_KEY=... python google_places.py --provincia "Almería" \
      --especialidad "clínica dental" --especialidad "fisioterapia" --out prospectos/almeria.csv
"""
import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.nationalPhoneNumber",
    "places.websiteUri", "places.rating", "places.userRatingCount", "places.businessStatus",
    "places.regularOpeningHours", "places.reviews", "places.googleMapsUri", "places.types",
    "nextPageToken",
])

# Cadenas, aseguradoras, hospitales y centros públicos: fuera del cliente ideal.
EXCLUIR_NOMBRE = re.compile(
    r"vitaldent|sanitas|milenium|dorsia|adeslas|clínica baviera|clinica baviera|ima dental|"
    r"unidental|dentix|funnydent|vivanta|quir[oó]n|hm hospitales|vithas|hospital|centro de salud|"
    r"servicio (andaluz|murciano|valenciano) de salud|podoactiva", re.I)
EXCLUIR_TIPO = {"hospital"}

# Frases de queja por no poder contactar por teléfono (ya en minúsculas).
QUEJAS = [
    r"no (cogen|coge|contestan|contesta|responden|responde|atienden|atiende)( el| al)? (tel[eé]fono|llamadas?)",
    r"(nadie|nunca) (coge|cogen|contesta|contestan|responde|responden)",
    r"tel[eé]fono (siempre )?(comunica|apagado|ocupado)|siempre comunica|comunica siempre",
    r"imposible (contactar|pedir cita|localizar|hablar|comunicar)",
    r"no hay (manera|forma) de (contactar|pedir cita|hablar|comunicar)",
    r"(llam[eé]|llamo|llam[aá]ndo|llamadas?) (varias|muchas|mil|infinitas) veces",
    r"(tardan|tardaron) (días|dias|mucho) en (contestar|responder|devolver)",
    r"no (me )?devuelven (la |las )?llamadas?",
    r"dif[ií]cil (contactar|pedir cita|conseguir cita|localizarlos)",
    r"(atenci[oó]n|trato) telef[oó]nic[ao] (muy )?(mala|pésim[ao]|deficiente|lenta|nula)",
    r"no (hay|tienen) (nadie|forma).{0,20}tel[eé]fono",
]
QUEJAS_RE = [re.compile(q, re.I) for q in QUEJAS]


def post(api_key, body):
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": api_key, "X-Goog-FieldMask": FIELDS})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:400]
        sys.exit(f"Google Places respondió {e.code}: {detalle}")


def buscar(api_key, consulta, paginas):
    """Hasta `paginas` páginas de 20 resultados (Google limita a 60 por búsqueda)."""
    lugares, token = [], None
    for _ in range(paginas):
        body = {"textQuery": consulta, "languageCode": "es", "regionCode": "ES", "pageSize": 20}
        if token:
            body["pageToken"] = token
        data = post(api_key, body)
        lugares += data.get("places", [])
        token = data.get("nextPageToken")
        if not token:
            break
    return lugares


def quejas_telefono(reviews, meses=36, ahora=None):
    """Reseñas que se quejan del teléfono. Devuelve [{fecha, estrellas, texto}] sin datos del autor."""
    ahora = ahora or datetime.now(timezone.utc)
    limite = ahora - timedelta(days=30 * meses)
    out = []
    for r in reviews or []:
        texto = ((r.get("text") or {}).get("text") or (r.get("originalText") or {}).get("text") or "")
        if not texto or not any(q.search(texto) for q in QUEJAS_RE):
            continue
        fecha = r.get("publishTime", "")
        try:
            if datetime.fromisoformat(fecha.replace("Z", "+00:00")) < limite:
                continue
        except ValueError:
            pass
        out.append({"fecha": fecha[:10], "estrellas": r.get("rating"), "texto": " ".join(texto.split())[:240]})
    return out


def analizar_horario(horario):
    """Huecos del horario. day: 0=domingo ... 6=sábado (formato de Google)."""
    periodos = (horario or {}).get("periods") or []
    if not periodos:
        return {"conocido": False, "mediodia": False, "cierra_pronto": False, "sin_sabado": False, "resumen": "?"}
    por_dia = {}
    for p in periodos:
        o, c = p.get("open") or {}, p.get("close") or {}
        if "day" not in o or "hour" not in o:
            continue
        ini = o["hour"] * 60 + o.get("minute", 0)
        fin = (c.get("hour", 0) * 60 + c.get("minute", 0)) if c and c.get("day") == o["day"] else 24 * 60
        por_dia.setdefault(o["day"], []).append((ini, fin))
    laborables = [d for d in (1, 2, 3, 4, 5) if d in por_dia]
    mediodia = sum(
        1 for d in laborables
        if len(por_dia[d]) >= 2 and any(
            b[0] - a[1] >= 90 for a, b in zip(sorted(por_dia[d]), sorted(por_dia[d])[1:])))
    cierra_pronto = sum(1 for d in laborables if max(f for _, f in por_dia[d]) <= 18 * 60)
    res = "; ".join((horario.get("weekdayDescriptions") or [])[:6])
    return {
        "conocido": True,
        "mediodia": mediodia >= 3,
        "cierra_pronto": cierra_pronto >= 3,
        "sin_sabado": 6 not in por_dia,
        "resumen": res,
    }


def es_movil(tel):
    digitos = re.sub(r"\D", "", tel or "")
    digitos = digitos[2:] if digitos.startswith("34") and len(digitos) > 9 else digitos
    return len(digitos) == 9 and digitos[0] in "67"


def valor_especialidad(texto):
    t = texto.lower()
    if any(k in t for k in ("dental", "dentista", "odont", "ortodon", "implant", "estétic", "estetic", "dermat")):
        return 2
    return 1


def evaluar(place):
    """Puntúa una clínica. Devuelve None si no pertenece al cliente ideal."""
    nombre = (place.get("displayName") or {}).get("text", "")
    if not nombre or place.get("businessStatus", "OPERATIONAL") != "OPERATIONAL":
        return None
    if EXCLUIR_NOMBRE.search(nombre) or EXCLUIR_TIPO & set(place.get("types") or []):
        return None
    quejas = quejas_telefono(place.get("reviews"))
    h = analizar_horario(place.get("regularOpeningHours"))
    n_res = place.get("userRatingCount") or 0
    senales = []
    for q in quejas:
        senales.append(f"Reseña Google ({q['fecha']}, {q['estrellas']}★): «{q['texto']}»")
    if h["mediodia"]:
        senales.append("Cierra a mediodía entre semana")
    if h["cierra_pronto"]:
        senales.append("Cierra a las 18:00 o antes entre semana")
    if h["sin_sabado"] and h["conocido"]:
        senales.append("No abre los sábados")
    if n_res > 100:
        senales.append(f"{n_res} reseñas en Google (demanda alta)")
    estructural = h["mediodia"] or h["cierra_pronto"] or (h["sin_sabado"] and n_res > 100)
    if quejas:
        prioridad, base = "Alta", 5
    elif estructural:
        prioridad, base = "Media", 3
    else:
        prioridad, base = "Por verificar", 1
    tel = place.get("nationalPhoneNumber", "")
    movil = es_movil(tel)
    puntos = base + valor_especialidad(nombre + " " + " ".join(place.get("types") or [])) + (1 if movil else 0) \
        + (1 if n_res > 100 else 0)
    return {
        "potencial": min(puntos, 10), "prioridad": prioridad, "nombre": nombre,
        "direccion": place.get("formattedAddress", ""), "web": place.get("websiteUri", ""),
        "telefono": tel, "movil_whatsapp": "sí" if movil else ("no" if tel else "?"),
        "valoracion": place.get("rating", ""), "n_resenas": n_res, "horario": h["resumen"],
        "señales": " | ".join(senales) or "ninguna comprobada", "fuente": place.get("googleMapsUri", ""),
        "_quejas": len(quejas), "_señales": len(senales),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provincia", required=True)
    ap.add_argument("--especialidad", action="append", required=True)
    ap.add_argument("--paginas", type=int, default=2, help="páginas de 20 por consulta (máx. 3)")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    key = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    if not key:
        sys.exit("Falta GOOGLE_PLACES_API_KEY (ver SKILL.md: cómo conseguirla).")

    vistos, filas, descartadas, peticiones = set(), [], 0, 0
    for esp in a.especialidad:
        for p in buscar(key, f"{esp} en {a.provincia}, España", max(1, min(a.paginas, 3))):
            peticiones += 1
            if p.get("id") in vistos:
                continue
            vistos.add(p.get("id"))
            r = evaluar(p)
            if r:
                filas.append(r)
            else:
                descartadas += 1
    orden = {"Alta": 0, "Media": 1, "Por verificar": 2}
    filas.sort(key=lambda r: (-r["potencial"], orden[r["prioridad"]], -r["_señales"], -r["n_resenas"]))
    cols = ["ranking", "potencial", "prioridad", "nombre", "direccion", "telefono", "movil_whatsapp",
            "valoracion", "n_resenas", "horario", "web", "señales", "fuente"]
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for i, r in enumerate(filas, 1):
                w.writerow({"ranking": i, **r})
    print(json.dumps({
        "provincia": a.provincia, "clinicas_validas": len(filas), "descartadas": descartadas,
        "con_queja_telefono": sum(1 for r in filas if r["_quejas"]),
        "csv": a.out, "top": [{k: v for k, v in r.items() if not k.startswith("_")} for r in filas[:10]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
