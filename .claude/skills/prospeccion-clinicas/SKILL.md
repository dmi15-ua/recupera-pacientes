---
name: prospeccion-clinicas
description: Busca clínicas médicas en España (dental, fisioterapia, ortopedia, podología, estética, etc.) que probablemente pierden pacientes por llamadas sin atender, las puntúa con señales públicas y entrega una lista ordenada con un borrador de primer contacto. Úsala cuando se pida buscar clientes, prospectos, leads o clínicas candidatas para RecuperaPacientes.
---

# Prospección de clínicas para RecuperaPacientes

RecuperaPacientes escribe por WhatsApp a quien llamó a una clínica y no fue atendido. La clínica
ideal es la que **recibe muchas llamadas y no puede cogerlas todas**.

## Entrada
Pregunta solo lo que falte (no repitas lo que ya te hayan dicho):
- **Zona**: ciudad, provincia o "toda España" (si es toda España, reparte por varias ciudades grandes).
- **Especialidad**: una o varias; por defecto todas las clínicas médicas privadas (dental, fisioterapia,
  ortopedia, podología, oftalmología, estética, psicología, medicina general...).
- **Cantidad**: por defecto 20 candidatas.

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

## Insiste hasta encontrar clínicas que lo necesiten
El objetivo no es listar clínicas, es encontrar **las que de verdad necesitan el agente**: las que
llegan a **4 puntos o más** con al menos una señal comprobada de llamadas sin atender. Una primera
tanda casi nunca basta, así que no te detengas ahí.

Repite por rondas hasta tener la cantidad pedida de candidatas con 4 o más, con un máximo de 6 rondas.
En cada ronda cambia de ángulo, en este orden:
1. **Otras consultas** en la misma zona: sinónimos de la queja ("llamé varias veces", "no hay manera
   de pedir cita", "tardan días en devolver la llamada", "siempre comunica") y de la especialidad.
2. **Otras especialidades** del listado, si el usuario no limitó a una.
3. **Otras fuentes**: Doctoralia, Masquemedicos, Páginas Amarillas, directorios de colegios
   profesionales y la propia web de la clínica (horario, falta de reserva online).
4. **Zonas cercanas**: municipios del área y provincias vecinas. Si pidieron "toda España", recorre
   las grandes ciudades una a una (Madrid, Barcelona, Valencia, Sevilla, Zaragoza, Málaga, Bilbao,
   Alicante, Murcia, Valladolid...).
5. **Clínicas ya vistas con puntuación baja**: revisa su web y reseñas con más detalle por si te
   saltaste una señal.

Al terminar cada ronda di en una línea cuántas llevas (por ejemplo "8 de 20 con 4 o más") y qué
ángulo probarás ahora. Pasa de ronda sin pedir permiso. Pregunta al usuario solo si tras las 6 rondas
no llegas al objetivo.

**Insistir es buscar más, no aflojar.** No subas la puntuación ni cuentes señales dudosas para
llegar a la cifra. Si tras las 6 rondas faltan candidatas, entrega las que cumplen, indica cuántas
faltan, qué rondas probaste y qué haría falta para encontrar más (por ejemplo, la API de Google Places).

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
- Si tras todas las rondas hay pocas, entrega lo que haya y dilo; no rellenes con candidatas dudosas.
- En la lista final, solo van las de 4 o más. Las de menos, si las quieres, en una hoja aparte del CSV
  (`descartadas`) con el motivo.
