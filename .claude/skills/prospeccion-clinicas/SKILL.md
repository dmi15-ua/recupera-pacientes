---
name: prospeccion-clinicas
description: Busca clínicas médicas en España (dental, fisioterapia, ortopedia, podología, estética, etc.) que probablemente pierden pacientes por llamadas sin atender, las puntúa con señales públicas y entrega una lista ordenada con un borrador de primer contacto. Úsala cuando se pida buscar clientes, prospectos, leads o clínicas candidatas para RecuperaPacientes.
---

# Prospección de clínicas para RecuperaPacientes

RecuperaPacientes escribe por WhatsApp a quien llamó a una clínica y no fue atendido. La clínica
ideal es la que **recibe muchas llamadas y no puede cogerlas todas**.

## Entrada
Pregunta solo lo que falte (no repitas lo que ya te hayan dicho):
- **Provincias**: las que indique el usuario (obligatorio; nunca "toda España").
- **Especialidad**: una o varias; por defecto todas las clínicas médicas privadas (dental, fisioterapia,
  ortopedia, podología, oftalmología, estética, psicología, medicina general...).
- **Cantidad**: la que salga dentro del presupuesto (ver abajo); no es un objetivo a cualquier precio.

## Cómo buscar
1. Con la búsqueda web, busca clínicas privadas en la zona y especialidad. Varía las consultas
   (`clínica dental {ciudad}`, `fisioterapia {ciudad} opiniones`, etc.).
2. Si existe la variable `GOOGLE_PLACES_API_KEY`, úsala para ficha, horario, valoración y nº de reseñas;
   si no, saca los datos de la web de la clínica y de lo que muestren los buscadores.
3. Para cada candidata abre su web y recoge solo datos **públicos de la empresa**:
   nombre, ciudad, especialidad, web, teléfono y email genéricos (info@, recepcion@), horario,
   si ofrece reserva online, si menciona WhatsApp.
4. Busca reseñas o menciones sobre el teléfono: "no cogen", "no contestan", "siempre comunica",
   "imposible contactar", "tardan en responder". Las fuentes que mejor funcionan en España son
   Doctoralia y Masquemedicos (en cada ficha, `/opiniones`); Google Maps no es accesible sin la API.
   La frase literal casi nunca aparece en clínicas privadas: busca variantes ("llamé varias veces",
   "no hay manera de pedir cita", "tardan días en devolver la llamada") y mira la nota de "atención
   al paciente". Los resultados de centros de salud públicos no valen: descártalos.

## Presupuesto fijo (no insistas)
El usuario da las **provincias**. Trabaja solo en esas, sin ampliar a otras zonas ni repetir rondas.
- **Máximo 4 búsquedas web por provincia** (por ejemplo: dental, fisioterapia, podología/ortopedia,
  y una de variantes de la queja) y como mucho 3 páginas abiertas por provincia.
- Para en cuanto llegues a ese tope, aunque haya pocas candidatas. No hagas más rondas por tu cuenta.
- Si una provincia no da nada, dilo en una línea y pasa a la siguiente.
- Al final, di cuántas búsquedas gastaste en total, y si quedó poca cosa, qué podría añadirse
  (otra provincia, otra especialidad); la decisión de seguir es del usuario.
- Si el usuario no da provincias, pídelas. No elijas ciudades tú.

**Lo que cuenta como candidata** son las de 4 puntos o más con al menos una señal comprobada. No
subas puntuaciones ni cuentes señales dudosas para llegar a ninguna cifra.

## Puntuación (0 a 10)
Suma, y no pases de 10:
| Señal | Puntos |
|---|---|
| Reseñas que se quejan de no poder contactar por teléfono (cita la reseña) | +4 |
| Horario telefónico limitado (cierra a mediodía, sin tardes, sin sábados) | +2 |
| Sin reserva online | +1 |
| Muchas reseñas (más de 100) con equipo pequeño: mucha demanda | +2 |
| Sin WhatsApp visible en la web | +1 |

Descarta o puntúa 0 si es un hospital o una gran cadena con centralita propia, si es una clínica
pública, o si no hay forma de contactar a la empresa.

**No inventes señales.** Si no pudiste comprobar algo, escribe `?` y no sumes. Cada señal que sume
debe llevar su fuente (URL). Una candidata sin ninguna señal comprobada no pasa de 2.

## Salida
1. Guarda un CSV en `prospectos/` (ya está en `.gitignore`: añádelo si falta) con columnas:
   `puntuacion, nombre, ciudad, especialidad, web, telefono, email, señales, fuentes, borrador`.
2. En el chat, una tabla corta con las 10 mejores (puntuación, nombre, ciudad, motivo en una frase)
   y la ruta del CSV.
3. Un **borrador de primer mensaje** por candidata, de 3-4 frases, personalizado con una señal real
   (por ejemplo, una reseña) y sin exagerar: propone una demo corta, no prometas resultados.

## Reglas
- Solo datos de la **empresa**. Nada de datos personales de profesionales o pacientes, ni listados
  de personas.
- No envíes nada: la skill solo prepara la lista y los borradores. El envío es decisión del usuario.
- Recuerda al entregar: las llamadas comerciales deben respetar la Lista Robinson y los correos
  comerciales la LSSI y el RGPD (base legal, forma de darse de baja). Dilo en una línea, sin sermón.
- Si hay pocas, entrega lo que haya y dilo; no rellenes con candidatas dudosas.
- En la lista final, solo van las de 4 o más. Las de menos, si las quieres, en una hoja aparte del CSV
  (`descartadas`) con el motivo.
