#!/usr/bin/env python3
"""Genera la hoja de comprobación (xlsx) a partir de una lista de clínicas.

Entrada: CSV con columnas  nombre,provincia,especialidad,telefono,horario_huecos
  horario_huecos = Sí | No | ?   (déjalo en ? si no lo has visto)

Uso:
  python generar_hoja.py clinicas.csv prospectos/hoja_comprobacion.xlsx

La hoja lleva fórmulas (prioridad, puntos y ranking) que se recalculan al anotar
lo que se ve en Google Maps. Solo usa openpyxl.
"""
import csv
import re
import sys
from urllib.parse import quote

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

VALOR2 = ("dental", "dentista", "odont", "ortodon", "implant", "estétic", "estetic", "dermat")
PRIMERAS = 10

COLS = ["Orden", "Comprobar primero", "Clínica", "Provincia", "Especialidad", "Teléfono", "Google Maps",
        "Valor especialidad (2 dental/estética, 1 resto)", "Móvil WhatsApp (1 sí, 0 no)",
        "Horario con huecos (mediodía, cierra pronto)", "Nº reseñas en Google",
        "Queja de teléfono en reseñas recientes", "Cita de la reseña (sin nombre del autor)",
        "Llamada de prueba: no cogieron", "¿Es cadena o franquicia?", "Notas",
        "Prioridad", "Puntos (0-10)", "Ranking"]
WIDTHS = [7, 11, 38, 11, 20, 14, 15, 14, 12, 16, 11, 16, 44, 13, 13, 28, 14, 9, 9]
F = "Arial"


def font(**k):
    return Font(name=F, size=10, **k)


def valor(especialidad):
    t = especialidad.lower()
    return 2 if any(k in t for k in VALOR2) else 1


def es_movil(tel):
    d = re.sub(r"\D", "", tel or "")
    d = d[2:] if d.startswith("34") and len(d) > 9 else d
    return 1 if len(d) == 9 and d[0] in "67" else 0


def puntos_iniciales(c):
    base = 3 if c["horario_huecos"] == "Sí" else 1
    return base + valor(c["especialidad"]) + es_movil(c["telefono"])


def leer(ruta):
    with open(ruta, newline="", encoding="utf-8") as f:
        filas = [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]
    for c in filas:
        c["horario_huecos"] = c.get("horario_huecos") or "?"
    # Más puntos primero; a igualdad, las que tienen teléfono publicado.
    filas.sort(key=lambda c: (-puntos_iniciales(c), not c.get("telefono")))
    return filas


def construir(clinicas, salida):
    wb = Workbook()
    ws = wb.active
    ws.title = "Comprobación"
    head = PatternFill("solid", fgColor="1F4E3D")
    amarillo = PatternFill("solid", fgColor="FFF2B3")
    azul = PatternFill("solid", fgColor="E8F0FE")
    verde = PatternFill("solid", fgColor="DDEFE3")
    lado = Side(style="thin", color="D0D0D0")
    borde = Border(left=lado, right=lado, top=lado, bottom=lado)

    ws.append(COLS)
    for c in range(1, len(COLS) + 1):
        x = ws.cell(1, c)
        x.font, x.fill, x.border = font(bold=True, color="FFFFFF"), head, borde
        x.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    ws.row_dimensions[1].height = 62

    n = len(clinicas)
    primero, ultimo = 2, 1 + n
    for i, c in enumerate(clinicas):
        r = 2 + i
        ws.cell(r, 1, i + 1)
        ws.cell(r, 2, "★ Primero" if i < PRIMERAS else "")
        ws.cell(r, 3, c["nombre"])
        ws.cell(r, 4, c["provincia"])
        ws.cell(r, 5, c["especialidad"])
        ws.cell(r, 6, c.get("telefono") or "—")
        ws.cell(r, 7, "Abrir en Maps").hyperlink = (
            "https://www.google.com/maps/search/?api=1&query=" + quote(f"{c['nombre']} {c['provincia']}"))
        ws.cell(r, 8, valor(c["especialidad"]))
        ws.cell(r, 9, es_movil(c.get("telefono")))
        ws.cell(r, 10, c["horario_huecos"])
        for col in range(11, 17):
            ws.cell(r, col).fill = amarillo
        ws.cell(r, 17, f'=IF(O{r}="Sí","Descartar",IF(OR(L{r}="Sí",N{r}="Sí"),"Alta",'
                       f'IF(J{r}="Sí","Media","Por verificar")))')
        ws.cell(r, 18, f'=IF(O{r}="Sí",0,MIN(10,IF(Q{r}="Alta",5,IF(Q{r}="Media",3,1))+H{r}+I{r}+IF(K{r}>100,1,0)))')
        ws.cell(r, 19, f'=IF(O{r}="Sí","",RANK(R{r},$R${primero}:$R${ultimo}))')
        for col in range(1, len(COLS) + 1):
            x = ws.cell(r, col)
            x.border = borde
            x.font = font(color="0000FF") if col in (8, 9, 10) else font()
            x.alignment = Alignment(wrap_text=True, vertical="top",
                                    horizontal="center" if col in (1, 8, 9, 10, 11, 12, 14, 15, 17, 18, 19) else None)
        for col in (8, 9, 10):
            ws.cell(r, col).fill = azul
        ws.cell(r, 7).font = font(color="0563C1", underline="single")
        if i < PRIMERAS:
            ws.cell(r, 2).fill = verde
            ws.cell(r, 2).font = font(bold=True, color="1F4E3D")
    for i, w in enumerate(WIDTHS, 1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = f"A1:S{ultimo}"

    si_no = DataValidation(type="list", formula1='"Sí,No"', allow_blank=True)
    si_no_q = DataValidation(type="list", formula1='"Sí,No,?"', allow_blank=True)
    ws.add_data_validation(si_no)
    ws.add_data_validation(si_no_q)
    si_no.add(f"L{primero}:L{ultimo}")
    si_no.add(f"N{primero}:O{ultimo}")
    si_no_q.add(f"J{primero}:J{ultimo}")
    rango = f"Q{primero}:Q{ultimo}"
    for texto, color in (("Alta", "F8C9C4"), ("Media", "FFE3A3"), ("Descartar", "DDDDDD")):
        ws.conditional_formatting.add(rango, CellIsRule(
            operator="equal", formula=[f'"{texto}"'], fill=PatternFill("solid", bgColor=color, fgColor=color)))

    g = wb.create_sheet("Cómo usarla")
    g.column_dimensions["A"].width = 30
    g.column_dimensions["B"].width = 95
    filas = [
        ("Qué es", "Hoja para comprobar a mano, en Google Maps, si estas clínicas pierden llamadas. Tú anotas lo que ves; el ranking se recalcula solo."),
        ("", ""),
        ("Colores", "Azul claro con texto azul = dato que preparé yo (puedes corregirlo). Amarillo = lo rellenas tú. Columnas Q, R y S = fórmulas, no las toques."),
        ("", ""),
        ("Paso 1", "Empieza por las filas con ★ Primero. Haz clic en «Abrir en Maps»."),
        ("Paso 2", "Columna K: apunta el nº total de reseñas que ves en la ficha. Columna J: mira el horario; si cierra a mediodía o antes de las 18:00 entre semana, pon Sí (si no, No)."),
        ("Paso 3", "Abre las reseñas, ordénalas por «Más recientes» y usa la lupa para buscar: teléfono, llamar, cogen, contestan, comunica, cita. Lee solo las de los últimos 3 años."),
        ("Paso 4", "Si alguna reseña reciente se queja de no poder contactar por teléfono: columna L = Sí y pega la frase en M. No copies el nombre del autor."),
        ("Paso 5 (opcional, la señal más fiable)", "Llama a la clínica 3 veces en horas distintas (mañana, mediodía, tarde). Si no cogen en ninguna, columna N = Sí. Si es una cadena o franquicia, columna O = Sí y se descarta."),
        ("Paso 6", "Mira Q (prioridad), R (puntos) y S (ranking). Ordena por S para ver las más potentes."),
        ("", ""),
        ("Cómo se puntúa", "Prioridad: Alta (queja en reseñas o llamada de prueba sin respuesta) 5 · Media (horario con huecos) 3 · Por verificar 1. Más: valor de la especialidad (H), móvil (I) y +1 si hay más de 100 reseñas en Google. Máximo 10. Una cadena puntúa 0."),
        ("Ojo", "Los puntos iniciales salen solo de datos de directorio, sin reseñas de Google. Es un ranking de hipótesis: cambiará cuando anotes lo que ves."),
        ("", ""),
        ("Ejemplo de fila rellenada", "Clínica Dental Ejemplo · J: Sí · K: 187 · L: Sí · M: «Llamé tres días seguidos y no cogen el teléfono» · N: No · O: No → Prioridad Alta, 5 + 2 + 0 + 1 = 8 puntos."),
    ]
    for i, (a, b) in enumerate(filas, 1):
        g.cell(i, 1, a).font = font(bold=True)
        g.cell(i, 2, b).font = font()
        for col in (1, 2):
            g.cell(i, col).alignment = Alignment(vertical="top", wrap_text=True)
    g.cell(3, 2).fill = azul

    wb.calculation.fullCalcOnLoad = True
    wb.save(salida)
    return n


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(f"{construir(leer(sys.argv[1]), sys.argv[2])} clínicas en {sys.argv[2]}")
