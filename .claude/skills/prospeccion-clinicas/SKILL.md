---
name: prospeccion-clinicas
description: Prepara la prospección de clínicas médicas privadas en las provincias que indique el usuario - lista las clínicas, genera una hoja de comprobación (xlsx) para mirar sus reseñas de Google y su teléfono a mano, recalcula el ranking con lo que el usuario anota y redacta los mensajes de primer contacto para RecuperaPacientes. Úsala cuando se pida buscar clientes, prospectos, leads o clínicas candidatas.
---

# Prospección de clínicas para RecuperaPacientes

RecuperaPacientes escribe por WhatsApp a quien llamó a una clínica y no fue atendido. La clínica
ideal es la que **recibe muchas llamadas y no puede cogerlas todas**.

## Cómo funciona (y por qué así)
No hay forma gratuita y legítima de leer en bloque las reseñas de Google: la API oficial de Google
Places es de pago y raspar Google Maps incumple sus condiciones. El usuario no usa APIs de pago, así
que el reparto es este:

| Lo hace Claude | Lo hace el usuario (en Google Maps) |
|---|---|
| Lista las clínicas de la provincia con teléfono y, si aparece, horario | Mira las reseñas de Google y el horario de cada ficha |
| Genera la hoja de comprobación con enlaces a Maps | Anota nº de reseñas, quejas del teléfono, «Sin web» y llamadas de prueba |
| Recalcula el ranking con lo que anota | |
| Redacta los mensajes para las clínicas Alta y Media | |

**Evidencia:** una clínica solo sube de prioridad por lo que el usuario ha visto en Google o en una
llamada de prueba. Las reseñas de directorios o foros **no** cuentan como evidencia.

## Cliente ideal
- **Especialidades con más valor por paciente:** dental (ortodoncia, implantes, estética dental),
  medicina estética y dermatología, fisioterapia y osteopatía, podología, ortopedia.
- **Tipo de negocio:** clínicas privadas independientes o grupos locales de 1 a 3 centros.
- **Evitar:** franquicias y cadenas (Vitaldent, Sanitas, Dorsia...), hospitales, aseguradoras y centros
  públicos.

## Paso 1: listar las clínicas
- Pide las **provincias** al usuario. Obligatorio; nunca "toda España" ni elijas tú.
- **Presupuesto fijo:** máximo 4 búsquedas web por provincia (por ejemplo dental, fisioterapia, estética
  y podología/ortopedia). Sin rondas extra ni ampliar zonas por tu cuenta.
- De cada clínica recoge solo datos **públicos de la empresa**: nombre, especialidad, teléfono, y el
  horario si aparece. Descarta cadenas, hospitales y públicas. Lo que no sepas, déjalo en `?`.
- **Una búsqueda por clínica, solo para las 10 primeras** (además del presupuesto de listado): busca
  `{nombre} {municipio} web opiniones` y anota si aparece **web propia** (no un directorio) y si salen
  malas reseñas. Recuerda los límites: no puedes abrir Google Maps ni las webs, y "no aparece en la
  búsqueda" no prueba que no tenga web. Escribe `No encontrada`, nunca "no tiene". Esa casilla no
  suma puntos hasta que el usuario confirma `Sin web` en la ficha de Maps.
- Comprueba también si es **cadena** (grupo con varias clínicas en distintas provincias): `cadena = Sí`
  la descarta. Apunta en `notas` lo que encuentres (puntuaciones, direcciones contradictorias, el
  horario y de quién es). Si no hay malas reseñas, di claramente que no las has encontrado.
- Guarda la lista en un CSV con las columnas `nombre,provincia,especialidad,telefono,horario_huecos,web,cadena,notas`
  (las tres últimas son opcionales). `horario_huecos` es `Sí` solo si has visto que cierra a mediodía
  o antes de las 18:00 entre semana (o no abre sábados) **y es el horario de la clínica**; si no, `?`.

## Paso 2: generar la hoja
```bash
python .claude/skills/prospeccion-clinicas/scripts/generar_hoja.py clinicas.csv prospectos/hoja_comprobacion.xlsx
```
- Ordena las clínicas por puntos iniciales y marca las 10 primeras con ★. `prospectos/` está en `.gitignore`.
- La hoja lleva las fórmulas de prioridad, puntos y ranking, y una hoja «Cómo usarla».
- Si hay LibreOffice, recalcula para que los valores se vean al abrir; si no, Excel y Google Sheets
  calculan al abrir.
- Entrégala al usuario (`SendUserFile`) y explica en pocas líneas qué rellenar: nº de reseñas, si hay
  queja de teléfono en reseñas recientes (con la frase, sin nombre del autor), llamada de prueba y si
  es cadena.

## Paso 3: recalcular y clasificar
Cuando el usuario devuelva la hoja rellena, léela con `openpyxl` (dos cargas: fórmulas y
`data_only=True` tras recalcular) y entrega:
1. **El ranking** de las 5 mejores (10 si lo piden), con puntos y motivo, citando la frase de la reseña.
2. Un recuento honesto: cuántas Alta, Media, por verificar y descartadas.
3. Los mensajes (abajo) para las Alta y Media.

**Prioridad:** Alta = queja de teléfono en reseña reciente o llamada de prueba sin respuesta. Media =
horario con huecos. Por verificar = sin señales. Descartar = cadena.
**Puntos (0-10):** prioridad Alta 5 / Media 3 / Por verificar 1, + valor de la especialidad (dental o
estética 2, resto 1), + 1 si tiene móvil (6 o 7), + 1 si tiene más de 100 reseñas en Google, + 1 si el usuario confirma «Sin web».
Es un ranking de **hipótesis**: dilo siempre. Si hay pocas Alta, dilo; no las infles.

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
- Solo datos de la **empresa**. No guardes nombres de autores de reseñas ni de profesionales.
- No envíes nada: la skill prepara la lista, la hoja y los textos. El envío es decisión del usuario.
- Recuerda una vez, en una línea: las llamadas comerciales deben respetar la Lista Robinson y los
  correos y mensajes comerciales la LSSI y el RGPD (base legal y forma de darse de baja).
