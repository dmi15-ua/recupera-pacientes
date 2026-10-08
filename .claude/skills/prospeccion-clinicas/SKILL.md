---
name: prospeccion-clinicas
description: Busca clínicas médicas privadas en las provincias que indique el usuario (dental, estética, fisioterapia, podología, ortopedia...), las ordena por prioridad con señales públicas de que pierden llamadas y prepara mensajes de primer contacto y respuestas a objeciones para RecuperaPacientes. Úsala cuando se pida buscar clientes, prospectos, leads o clínicas candidatas.
---

# Prospección de clínicas para RecuperaPacientes

RecuperaPacientes escribe por WhatsApp a quien llamó a una clínica y no fue atendido. La clínica
ideal es la que **recibe muchas llamadas y no puede cogerlas todas**.

## Cliente ideal
- **Especialidades con más valor por paciente:** dental (ortodoncia, implantes, estética dental),
  medicina estética y dermatología, fisioterapia y osteopatía, podología, ortopedia.
- **Tipo de negocio:** clínicas privadas independientes o grupos locales de 1 a 3 centros: el dueño es
  accesible, decide rápido y tiene recepción propia.
- **Evitar:** grandes franquicias y cadenas (Vitaldent, Sanitas Dental, Dorsia...), hospitales y
  clínicas públicas. Tienen centralita corporativa y compras complejas.

## Entrada
- **Provincias**: las que indique el usuario. Obligatorio; si no las da, pídelas. Nunca "toda España"
  ni elijas ciudades tú.
- **Especialidades**: las que indique; por defecto, las del cliente ideal.

## Presupuesto fijo (no insistas)
- **Máximo 4 búsquedas web por provincia** y 3 páginas abiertas por provincia. Para al llegar al tope,
  aunque salgan pocas. Sin rondas extra ni ampliar a otras zonas por tu cuenta.
- Al terminar, di cuántas búsquedas gastaste y, si salió poco, qué podría añadirse (otra provincia u
  otra especialidad). Seguir lo decide el usuario.

## Cómo buscar
1. **Directorio (2 búsquedas):** localiza clínicas de la provincia por especialidad
   (`clínica dental {provincia}`, `fisioterapia {provincia}`, `clínica estética {provincia}`...).
   De cada una recoge solo datos **públicos de la empresa**: nombre, municipio, especialidad, web,
   teléfono, si el número es móvil (empieza por 6 o 7: puede recibir WhatsApp), email genérico
   (info@, recepcion@) y horario si aparece.
2. **Señales de pérdida de llamadas (2 búsquedas):** reseñas que se quejan del teléfono. Las fuentes
   que funcionan son Doctoralia y Masquemedicos (`/opiniones`). La frase literal casi nunca aparece:
   busca variantes ("llamé varias veces", "no hay manera de pedir cita", "tardan días en devolver la
   llamada"). Los centros de salud públicos no valen.
3. Lo que no puedas comprobar se queda en `?`. Sin acceso a Google Maps ni a las webs de las clínicas,
   a menudo no sabrás el horario real ni si hay reserva online ni si tienen bot. **Instagram no se
   puede verificar con la búsqueda web: no afirmes que una cuenta está activa.**

## Prioridad (es una hipótesis, no una cualificación)
Que una clínica tenga móvil en la web no prueba que pierda llamadas. Ordena así y dilo claramente:

| Prioridad | Cuándo |
|---|---|
| **Alta** | Al menos una reseña comprobada que se queja de no poder contactar por teléfono (cita la reseña y su URL) |
| **Media** | Sin queja comprobada, pero con señal estructural comprobada: horario con huecos (cierra a mediodía, sin tardes o sin sábados), sin reserva online, o mucha demanda (más de 100 reseñas) con equipo pequeño |
| **Por verificar** | Cumple el cliente ideal, pero sin ninguna señal comprobada |

Cada señal lleva su fuente. Si no la tienes, no la pongas. Descarta cadenas, hospitales y públicas.

## Salida
1. CSV en `prospectos/` (añade la carpeta a `.gitignore` si falta) con columnas:
   `prioridad, nombre, municipio, especialidad, web, telefono, movil_whatsapp, email, señales, fuentes, mensaje`.
2. En el chat, una tabla con todas, ordenadas por prioridad:

   | Clínica | Municipio | Teléfono | ¿Móvil/WhatsApp? | Prioridad | Motivo (con fuente) |

   y la ruta del CSV.
3. Un **mensaje de primer contacto** por clínica Alta o Media, listo para copiar, adaptado a su canal
   (WhatsApp si tiene móvil; si no, email o llamada). Usa una señal real si la hay.

## Mensajes
Reglas: 3 o 4 frases, tono cercano, una sola petición (una demo corta), nada de exagerar. **No
prometas lo que el producto no hace:**
- Escribe al paciente **a los pocos minutos** de la llamada perdida (espera por si le cogen). No digas
  "en 15 segundos".
- De noche **no** escribe: aplaza el mensaje a la franja permitida. No digas que atiende "fuera de horario".
- La puesta en marcha depende de que Meta apruebe la plantilla de WhatsApp: no prometas plazos.
- **No inventes precio ni prueba gratuita.** Si el usuario no los ha definido, ofrece solo una demo y
  deja `[PRECIO]` o `[PRUEBA]` marcados para que los complete.

**WhatsApp:**
```text
Hola, buenos días. Escribo al responsable de recepción de [Clínica]. [Si hay señal real: He visto que
algunos pacientes comentan que cuesta contactar por teléfono.] Tenemos una herramienta que escribe por
WhatsApp, a los pocos minutos, a quien llamó y no pudo ser atendido, para no perder esa cita. ¿Le puedo
enseñar una demo de 5 minutos?
```

**Instagram o email:**
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
- Solo datos de la **empresa**. No incluyas nombres de profesionales ni de pacientes.
- No envíes nada: la skill prepara la lista y los textos. El envío es decisión del usuario.
- Recuerda una vez, en una línea: las llamadas comerciales deben respetar la Lista Robinson y los
  correos y mensajes comerciales la LSSI y el RGPD (base legal y forma de darse de baja).
- Si hay pocas clínicas, entrega lo que haya y dilo; no rellenes con candidatas dudosas.
