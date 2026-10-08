---
name: prospeccion-clinicas
description: Busca clínicas médicas privadas en las provincias que indique el usuario usando la API oficial de Google Places (valoraciones, horarios y teléfonos de Google), detecta quejas por no coger el teléfono, las clasifica y prepara mensajes de primer contacto para RecuperaPacientes. Úsala cuando se pida buscar clientes, prospectos, leads o clínicas candidatas.
---

# Prospección de clínicas con Google Places

RecuperaPacientes escribe por WhatsApp a quien llamó a una clínica y no fue atendido. La clínica
ideal es la que **recibe muchas llamadas y no puede cogerlas todas**.

**Única fuente: Google** (reseñas, horario, teléfono y web de la ficha de Google Maps), a través de la
API oficial. No uses directorios, foros ni búsqueda web general para encontrar clínicas o reseñas.
No hagas scraping de la web de Google Maps: incumple sus condiciones, se bloquea y no es estable.

## Antes de empezar
1. Hace falta la variable `GOOGLE_PLACES_API_KEY`. Si no existe, **para y explica al usuario cómo
   conseguirla**, sin buscar alternativas:
   1. En <https://console.cloud.google.com> crear un proyecto y activar la facturación (la API tiene
      una cuota gratuita mensual; comprobar los precios vigentes de *Places API (New)* antes de usarla).
   2. Activar **Places API (New)**.
   3. Crear una clave en *APIs y servicios → Credenciales* y restringirla a esa API.
   4. Ponerla como variable de entorno `GOOGLE_PLACES_API_KEY` en el entorno de la sesión.
2. El entorno debe poder llegar a `places.googleapis.com` (en este entorno ya llega).
3. Pide las **provincias** al usuario. Obligatorio; nunca "toda España" ni elijas tú.

## Cliente ideal
- **Especialidades con más valor por paciente:** dental (ortodoncia, implantes, estética dental),
  medicina estética y dermatología, fisioterapia y osteopatía, podología, ortopedia.
- **Tipo de negocio:** clínicas privadas independientes o grupos locales de 1 a 3 centros.
- **Evitar:** franquicias y cadenas (Vitaldent, Sanitas, Dorsia...), hospitales, aseguradoras y centros
  públicos. El script ya descarta los nombres más comunes; revisa a mano lo que se le escape.

## Cómo se ejecuta
Una ejecución por provincia (cada una cuesta peticiones a Google; no repitas sin motivo):

```bash
python .claude/skills/prospeccion-clinicas/scripts/google_places.py \
  --provincia "Almería" --especialidad "clínica dental" --especialidad "fisioterapia" \
  --especialidad "clínica estética" --especialidad "podología" --paginas 2 \
  --out prospectos/almeria.csv
```

- Cada especialidad lanza una búsqueda de hasta `--paginas` páginas de 20 clínicas (máx. 3).
- Devuelve un JSON con el resumen y el top 10, y guarda el CSV completo. `prospectos/` ya está en `.gitignore`.
- **Presupuesto:** 4 especialidades × 2 páginas = 8 peticiones por provincia. No pases de ahí sin que
  el usuario lo pida.

## Qué calcula (no lo recalcules a mano)
- **Quejas de teléfono** en las reseñas de Google (la API da hasta 5 por clínica, las más relevantes;
  solo cuentan las de los últimos 36 meses). Se guarda la frase, la fecha y las estrellas; **nunca el
  nombre del autor**.
- **Horario** de Google: cierra a mediodía entre semana, cierra a las 18:00 o antes, no abre sábados.
- **Demanda**: más de 100 reseñas. **Móvil**: número que empieza por 6 o 7 (puede recibir WhatsApp).

| Prioridad | Cuándo |
|---|---|
| **Alta** | Al menos una reseña reciente de Google que se queja del teléfono |
| **Media** | Sin queja, pero cierra a mediodía o pronto entre semana, o no abre sábados con más de 100 reseñas |
| **Por verificar** | Cumple el cliente ideal sin ninguna señal |

**Puntuación de potencial (0 a 10):** prioridad Alta 5 / Media 3 / Por verificar 1, + valor por paciente
(dental o estética 2; fisioterapia, podología u ortopedia 1), + 1 si tiene móvil, + 1 si tiene más de
100 reseñas. Desempate: más señales comprobadas.

## Cómo informar
1. **Primero el ranking** de las 5 mejores (10 si lo piden), con puntos y motivo, citando la frase de
   la reseña y el enlace de Google Maps (`fuente`).
2. Un recuento honesto: cuántas clínicas válidas, cuántas con queja de teléfono, cuántas descartadas.
3. La ruta del CSV.
4. **Sé claro con los límites**: Google solo da 5 reseñas por clínica, así que que una clínica no tenga
   queja no significa que no pierda llamadas, y es un ranking de hipótesis. Si hay pocas Alta, dilo;
   no las inventes ni las infles.
5. Mensajes de primer contacto para las Alta y Media (abajo).

## Mensajes
Reglas: 3 o 4 frases, tono cercano, una sola petición (una demo corta), nada de exagerar. **No
prometas lo que el producto no hace:**
- Escribe al paciente **a los pocos minutos** de la llamada perdida (espera por si le cogen). No digas
  "en 15 segundos".
- De noche **no** escribe: aplaza el mensaje a la franja permitida. No digas que atiende "fuera de horario".
- La puesta en marcha depende de que Meta apruebe la plantilla de WhatsApp: no prometas plazos.
- **No inventes precio ni prueba gratuita.** Si el usuario no los ha definido, ofrece solo una demo y
  deja `[PRECIO]` o `[PRUEBA]` marcados.
- **No cites ni imites a un cliente concreto de una reseña.** Habla de "algunos pacientes comentan que
  cuesta contactar por teléfono".

**WhatsApp (si tiene móvil):**
```text
Hola, buenos días. Escribo al responsable de recepción de [Clínica]. [Si hay queja: He visto que
algunos pacientes comentan que cuesta contactar por teléfono.] Tenemos una herramienta que escribe por
WhatsApp, a los pocos minutos, a quien llamó y no pudo ser atendido, para no perder esa cita. ¿Le puedo
enseñar una demo de 5 minutos?
```

**Email o llamada (si solo tiene fijo):**
```text
Hola, equipo de [Clínica]. Una pregunta rápida: cuando recepción está ocupada y alguien llama sin que
le cojan, ¿le escribís por WhatsApp para no perder la cita? Ayudamos a clínicas de [provincia] con una
herramienta que lo hace sola a los pocos minutos y deja la solicitud lista para que recepción la
confirme. ¿Os enseño una demo corta?
```

## Respuestas a objeciones
- **"Ya tenemos recepcionista."** No la sustituye: ayuda justo cuando está atendiendo a alguien en
  consulta o cobrando y no puede coger otra llamada. Recepción sigue confirmando las citas.
- **"¿Y si dice algo incorrecto?"** Solo usa la información que la clínica nos da. Si no sabe algo, lo
  dice y avisa a recepción para que responda. No confirma citas ni da consejos médicos.
- **"¿Es difícil de instalar?"** La configuración la hacemos nosotros con los datos de la clínica; lo
  que puede tardar es la aprobación de la plantilla por parte de Meta. No des un plazo concreto.
- **"¿Cuánto cuesta?"** Solo responde si el usuario ha definido precio. Si no, di que se lo explicas
  en la demo.

## Reglas
- Solo datos de la **empresa** (nombre, dirección, teléfono, web, horario, valoración). No guardes
  nombres de autores de reseñas ni de profesionales.
- Las reseñas de Google se usan para detectar un problema de contacto, no se republican.
  Cumple las condiciones de la API de Google Places (no cachear datos más de lo permitido).
- No envíes nada: la skill prepara la lista y los textos. El envío es decisión del usuario.
- Recuerda una vez, en una línea: las llamadas comerciales deben respetar la Lista Robinson y los
  correos y mensajes comerciales la LSSI y el RGPD (base legal y forma de darse de baja).
