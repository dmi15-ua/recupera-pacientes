# Contrato de encargado del tratamiento (art. 28 RGPD)

## 1. Objeto

La Clínica contrata los servicios de **RecuperaPacientes**: cuando un paciente llama a la clínica y no
es atendido, el servicio le escribe por WhatsApp, responde sus dudas con la información que la Clínica
ha facilitado, recoge una solicitud de cita y avisa a recepción. Para prestarlo, el Encargado trata
datos personales por cuenta de la Clínica. Este contrato regula ese tratamiento.

## 2. Descripción del tratamiento

| | |
|---|---|
| **Finalidad** | Atender por WhatsApp a pacientes que han llamado y no han sido atendidos o que escriben a la clínica, responder consultas y recoger solicitudes de cita para que recepción las confirme. |
| **Interesados** | Pacientes y personas que llaman o escriben a la Clínica. |
| **Datos tratados** | Número de teléfono, nombre (si lo facilitan), contenido de los mensajes de WhatsApp (incluida la transcripción de notas de voz), motivo de la consulta, preferencia de horario, estado de la conversación y fecha de las llamadas perdidas. |
| **Categorías especiales** | Los mensajes pueden revelar datos de salud (por ejemplo, el motivo de una visita). El servicio **no solicita** historial clínico, diagnósticos, DNI ni tarjeta sanitaria. |
| **Operaciones** | Recogida, registro, consulta, uso, transmisión a los subencargados del punto 7, conservación y supresión. |
| **Duración** | Mientras dure la prestación del servicio. |
| **Conservación** | Las conversaciones inactivas se cierran a los 3 días y **se borran automáticamente a los 180 días**. Las personas que escriben BAJA dejan de recibir mensajes proactivos. [Confirmar plazos con la Clínica.] |

## 3. Obligaciones del Encargado

El Encargado se compromete a:

1. **Tratar los datos solo siguiendo las instrucciones documentadas de la Clínica**, incluido lo relativo a transferencias internacionales. Este contrato y la configuración que la Clínica indica en su ficha son esas instrucciones. Si considera que una instrucción infringe la normativa, se lo comunicará.
2. **No usar los datos para fines propios**, ni para entrenar modelos, ni comunicarlos a terceros salvo los subencargados autorizados.
3. **Garantizar la confidencialidad** de las personas que accedan a los datos, que estarán sujetas a un deber de secreto.
4. **Aplicar las medidas de seguridad del Anexo II** (art. 32 RGPD).
5. **Respetar las condiciones de subencargo** del punto 7.
6. **Asistir a la Clínica** para atender los derechos de los interesados (acceso, rectificación, supresión, oposición, limitación y portabilidad). Si un interesado se dirige al Encargado, lo trasladará a la Clínica **en un máximo de [3] días hábiles** y no responderá por su cuenta.
7. **Notificar las violaciones de seguridad** a la Clínica **sin dilación indebida y, como máximo, en [48] horas** desde que tenga conocimiento, con la información de que disponga para que la Clínica cumpla sus obligaciones.
8. **Asistir a la Clínica** en las evaluaciones de impacto y consultas previas que procedan.
9. **Suprimir o devolver los datos** al terminar el servicio, a elección de la Clínica, y borrar las copias existentes, salvo que la ley obligue a conservarlos. Plazo: [30] días desde la baja.
10. **Poner a disposición de la Clínica la información** necesaria para demostrar el cumplimiento y permitir **auditorías razonables**, con preaviso de [15] días y sin perturbar la actividad.
11. **Llevar un registro** de las actividades de tratamiento realizadas por cuenta de la Clínica.

## 4. Obligaciones de la Clínica

La Clínica, como responsable, se compromete a:

1. Contar con una **base jurídica** válida para tratar los datos, incluidos los de salud (art. 9 RGPD), y para escribir por WhatsApp a quien ha llamado a la clínica. [Revisar la base con el asesor de la Clínica.]
2. **Informar a los pacientes** de este tratamiento, incluido que la atención por WhatsApp la realiza un asistente automático y que pueden pedir hablar con una persona del equipo.
3. Facilitar al Encargado **solo la información necesaria** para el servicio y no incluir en ella datos clínicos de pacientes.
4. Atender el ejercicio de derechos de los interesados.
5. Mantener la **confidencialidad de los códigos de acceso** al panel de recepción y avisar al Encargado si se han comprometido.
6. Supervisar las solicitudes de cita y las respuestas del asistente. El asistente **no confirma citas ni da consejo médico**; la confirmación y cualquier decisión clínica corresponden a la Clínica.

## 5. Transferencias internacionales

Algunos subencargados pueden tratar datos fuera del Espacio Económico Europeo. En ese caso, el Encargado
se asegurará de que existe una garantía adecuada (decisión de adecuación o cláusulas contractuales tipo)
y la Clínica lo autoriza con la firma de este contrato. [Confirmar la ubicación de cada subencargado.]

## 6. Responsabilidad

Cada parte responde de los daños que cause por incumplir el RGPD y este contrato, en los términos del
art. 82 RGPD. [Revisar con el asesor cualquier límite de responsabilidad que quiera añadirse.]

## 7. Subencargados

La Clínica **autoriza** los subencargados del Anexo III. El Encargado informará a la Clínica de cualquier
cambio con [15] días de antelación; la Clínica podrá oponerse por motivos razonables y, si no hay
alternativa, resolver el contrato. Cada subencargado queda sujeto a obligaciones equivalentes a las de
este contrato.

## 8. Duración y terminación

El contrato dura lo que dure el servicio. Al terminar, se aplica el punto 3.9.

## 9. Ley aplicable y jurisdicción

Legislación española. Para cualquier conflicto, los juzgados y tribunales de [ciudad].

Firmado en dos ejemplares.

| La Clínica | El Encargado |
|---|---|
| Fdo.: [nombre] | Fdo.: [nombre] |

---

## Anexo I. Datos y finalidad

Ver el punto 2.

## Anexo II. Medidas de seguridad

Medidas que el servicio aplica hoy. Quita las que no se cumplan y añade las que falten:

- **Control de acceso:** el panel de recepción exige un código único por clínica; cada clínica solo ve
  sus conversaciones. El panel de administración exige un token propio.
- **Autenticación de los canales:** los avisos entrantes de WhatsApp y de Twilio se aceptan solo con firma
  válida, y los de la centralita, solo con un token secreto.
- **Minimización:** no se solicita historial clínico, DNI ni tarjeta sanitaria. Los avisos a recepción por
  Telegram incluyen solo nombre, teléfono y motivo; el detalle de la conversación se consulta en el panel.
- **Conservación limitada:** cierre automático a los 3 días de inactividad y borrado a los 180 días.
- **Supervisión humana:** el asistente pasa la conversación a una persona del equipo si el paciente lo
  pide, hay una queja o no puede resolver; recepción puede tomar el control en cualquier momento.
- **Límites del asistente:** solo responde con la información facilitada por la Clínica; ante una duda,
  no inventa y avisa a recepción. Hay un tope diario de llamadas al modelo por conversación.
- **Modelo de lenguaje:** se usa con un proyecto de facturación activada [confirmar que los datos no se
  usan para entrenar según las condiciones vigentes del proveedor].
- **Cifrado en tránsito:** [confirmar HTTPS en todos los puntos]. **Cifrado en reposo:** [confirmar el
  del proveedor de base de datos].
- **Copias de seguridad y recuperación:** [describir].
- **Gestión de incidentes:** [describir quién avisa a quién y en cuánto tiempo].

## Anexo III. Subencargados autorizados

| Subencargado | Servicio | Datos | Ubicación / garantía |
|---|---|---|---|
| Meta Platforms Ireland Ltd. (WhatsApp Business Platform) | Envío y recepción de mensajes de WhatsApp | Teléfono, mensajes, nombre de perfil | [confirmar] |
| Google (Gemini API) | Generación de respuestas y transcripción de notas de voz | Texto de la conversación y audio de las notas de voz | [confirmar] |
| [Proveedor de alojamiento y base de datos, p. ej. Railway o Supabase] | Alojamiento de la aplicación y almacenamiento | Todos los datos del punto 2 | [confirmar región] |
| Telegram | Avisos a recepción | Nombre, teléfono y motivo | [confirmar] |
| Twilio (solo si la Clínica usa un número de Twilio) | Telefonía y detección de llamadas perdidas | Número de teléfono de quien llama | [confirmar] |

---

## Qué revisar antes de usarlo

1. Razón social, NIF y domicilio de las dos partes, y la ciudad de los tribunales.
2. Plazos: 3 días hábiles (derechos), 48 horas (violaciones), 30 días (devolución o borrado), 15 días
   (cambios de subencargados y auditorías).
3. **Base jurídica de la clínica** para tratar datos de salud y para escribir a quien llamó. Es su
   responsabilidad, pero conviene que lo hable con su asesor.
4. **Evaluación de impacto (EIPD):** al tratar datos de salud a cierta escala puede ser exigible.
   Pregúntalo al profesional que lo revise.
5. Que los **acuerdos con los subencargados existen de verdad**: aceptar sus condiciones de
   tratamiento de datos de Meta, Google, tu proveedor de alojamiento, Telegram y Twilio.
6. Los puntos de «confirmar» del Anexo II y III.
7. Si vas a firmar como persona física o como sociedad: afecta a la responsabilidad.
