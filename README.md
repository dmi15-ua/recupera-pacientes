# RecuperaPacientes

Convierte las llamadas perdidas de una clínica en citas. Cuando nadie coge el teléfono, escribe
al paciente por WhatsApp, le atiende con un asistente que solo usa la información de la clínica
y deja la solicitud de cita lista para que recepción la confirme.

```
Llamada perdida ──► espera 2 min ──► ¿hay que escribir? ──► plantilla de WhatsApp
 (Twilio o centralita)  (por si le cogen)  (baja, fijo, repetida,       │
                                            horario, ya habla con él)    ▼
                                                              El paciente responde
                                                                         │
            urgencia vital ◄── filtro sin IA ──┬── BAJA ──► se borra de envíos
            (112 + aviso)                      ▼
                                   Asistente (Gemini Flash-Lite + herramientas)
                                   ├─ registrar_solicitud_cita ─► aviso a recepción
                                   ├─ pasar_a_humano ───────────► el bot se calla
                                   └─ marcar_urgencia ──────────► aviso prioritario
```

## Qué hace (y qué no)

- **Espera antes de escribir** (2 min): si el paciente vuelve a llamar y le cogen, no se le escribe.
- **Agrupa** llamadas repetidas del mismo número en un solo mensaje.
- **No escribe de noche**: fuera de la franja permitida (por defecto 9:00–21:00) el mensaje se aplaza.
- **Fijos y números sin WhatsApp**: avisa a recepción para devolver la llamada.
- **Agrupa mensajes seguidos** del paciente y contesta una vez.
- **Transcribe notas de voz.**
- **Urgencias vitales** detectadas por reglas (sin IA): responde con el 112 y avisa.
- **BAJA**: el paciente deja de recibir mensajes proactivos.
- **Recepción manda**: si alguien del equipo escribe (panel o app de WhatsApp con coexistencia), el bot se calla 12 h.
- **No confirma citas**: no tiene la agenda, así que recoge nombre, motivo y preferencia y recepción da el hueco.
- **Topes de coste**: 20 llamadas al LLM por conversación y día; si se supera, pasa a una persona.
- **Retención**: cierra conversaciones inactivas a los 3 días y borra todo a los 180.

## Coste

| Pieza | Coste |
|---|---|
| Base de datos | Postgres en Railway (entra en el consumo del plan) o Supabase gratis. |
| Servidor | Railway (unos 5 $/mes) o el nivel gratuito de Oracle Cloud. El servidor no guarda datos: todo va a Postgres. |
| WhatsApp | Las respuestas al paciente son gratis. Se paga la plantilla inicial (céntimos por llamada perdida; mira la tabla de precios de Meta para España). |
| LLM | Gemini Flash-Lite: fracciones de céntimo por conversación. **Con facturación activada** (el nivel gratis puede usar los datos para entrenar). |
| Avisos | Telegram: gratis. |
| Telefonía | Si la centralita ya manda webhooks, 0 €. Con Twilio, número + minutos desviados. |

## Probar en local (gratis, sin credenciales)

```bash
python -m pip install -r requirements.txt
```

```bash
cp clinicas.example.json clinicas.json
```

Crea un `.env` con `ADMIN_TOKEN=dev-admin` y arranca:

```bash
python -m uvicorn app.main:app --port 8000
```

Sin `WA_TOKEN` los WhatsApp se imprimen en consola. Simula una llamada y una respuesta:

```bash
curl -X POST localhost:8000/api/dev/llamada -H "Authorization: Bearer dev-admin" -H "Content-Type: application/json" -d '{"clinica_id":"demo-dental","telefono":"600111222"}'
```

```bash
curl -X POST localhost:8000/api/dev/mensaje -H "Authorization: Bearer dev-admin" -H "Content-Type: application/json" -d '{"clinica_id":"demo-dental","telefono":"600111222","texto":"Hola, ¿cuánto cuesta una limpieza?"}'
```

- Landing: <http://localhost:8000>
- Ficha de alta para clínicas: <http://localhost:8000/alta>
- Dashboard de administración: <http://localhost:8000/admin> (código: `ADMIN_TOKEN`)
- Panel de recepción: <http://localhost:8000/panel> (código: el `panel_token` de la clínica)

Tests (con SQLite):

```bash
python -m pytest -q
```

Para pasarlos también contra Postgres, pon `TEST_DATABASE_URL` con una URL accesible desde tu
ordenador (en Railway, `DATABASE_PUBLIC_URL`). Usan el
schema `rp_test`, que borran entero; nunca tocan `rp`.

## Poner en producción

1. **Base de datos (Postgres)**: vale cualquiera. Al arrancar, la app crea sus tablas en el
   schema `rp` (no toca nada de `public`, donde puede haber otras cosas, como n8n).
   - **Railway**: añade un servicio Postgres al proyecto y, en las variables de la app, pon
     `DATABASE_URL=${{Postgres.DATABASE_URL}}`. Las tablas se ven en la pestaña *Data* del Postgres
     y en `/admin`.
   - **Supabase**: *Connect → URI*, modo **Session pooler** → `DATABASE_URL`.
2. **Servidor (Railway)**: crea un servicio desde el repo (usa el `Dockerfile`), pon las variables
   de `.env.example` y un dominio. **Una sola réplica**: el bucle de tareas vive dentro del proceso.
   No hace falta volumen.
3. **Gemini**: crea una API key en un proyecto de Google Cloud con facturación → `GEMINI_API_KEY`.
4. **WhatsApp (Meta)**:
   - Crea una app en developers.facebook.com con el producto WhatsApp y registra el número de la
     clínica. Si recepción quiere seguir usando la app WhatsApp Business en el móvil, usa la
     incorporación con **coexistencia**.
   - Token permanente de un usuario del sistema → `WA_TOKEN`. Secreto de la app → `WA_APP_SECRET`.
   - Webhook: `https://tu-dominio/webhooks/whatsapp`, con un token que inventes → `WA_VERIFY_TOKEN`.
     Suscribe `messages` (y `smb_message_echoes` si usas coexistencia).
   - Crea la plantilla `llamada_perdida` (categoría utilidad, idioma `es`) con este texto:
     > Hola, somos {{1}}. Hemos visto tu llamada y no hemos podido atenderte. ¿En qué te podemos
     > ayudar? Responde a este mensaje y te atendemos por aquí. Si no quieres recibir mensajes,
     > responde BAJA.
   - Pon el `phone_number_id` en `wa_phone_number_id` de la clínica.
5. **Llamadas**, una de dos:
   - **Centralita con webhooks**: que haga `POST https://tu-dominio/webhooks/llamada` con la cabecera
     `X-Webhook-Token: <CALL_WEBHOOK_TOKEN>` y el cuerpo
     `{"to": "+34910000000", "from": "+34600111222", "id": "id-unico", "estado": "perdida"}`
     (o `"atendida"` para cancelar el mensaje si luego le cogen).
   - **Twilio**: compra un número, apunta su *Voice webhook* a `https://tu-dominio/webhooks/twilio/voz`,
     pon `TWILIO_AUTH_TOKEN` y en la clínica `numeros_llamada` (el de Twilio) y `telefono_recepcion`
     (al que se pasa la llamada). Twilio hace sonar recepción y, si nadie coge, avisa al paciente
     de que le escribirán por WhatsApp.
6. **Avisos**: crea un bot con @BotFather → `TELEGRAM_BOT_TOKEN`. Añádelo al grupo de recepción y pon
   el id del grupo en `telegram_chat_id` de la clínica. `OWNER_TELEGRAM_CHAT_ID` recibe los leads de la landing.
7. **Privacidad**: completa `web/privacidad.html` y firma el contrato de encargado del tratamiento
   con cada clínica.

## Alta de una clínica nueva

1. Tras la demo, envía a la clínica el enlace `https://tu-dominio/alta`. Rellena servicios con
   precio, horario, preguntas frecuentes (seguros, parking, financiación…) y cómo debe hablar el asistente.
2. Te llega un aviso por Telegram. En `/admin → Fichas de alta` ves la ficha y **lo que leerá el
   asistente**. Pulsa *Crear clínica*: se crea inactiva y con su código para el panel de recepción.
3. Conecta su WhatsApp y pon el `wa_phone_number_id` en Supabase (*Table Editor → schema `rp` →
   `clinics`*). Desde ahí puedes retocar precios, horario o instrucciones cuando quieras: se aplica al momento.
4. En `/admin → Clínicas`, *Activar*. El dashboard muestra por clínica las llamadas perdidas,
   los WhatsApp enviados, las conversaciones y las citas pedidas de los últimos 30 días.

## Estructura

```
app/
  main.py        rutas: webhooks, panel, admin, altas, leads, simulador
  onboarding.py  ficha de alta -> clínica (texto que lee el asistente)
  service.py     reglas: llamadas perdidas, mensajes entrantes, bucle de tareas
  agent.py       prompt + herramientas del asistente
  llm.py         cliente de Gemini (function calling)
  whatsapp.py    WhatsApp Cloud API: envío, firma y parseo de webhooks
  telephony.py   Twilio (firma, TwiML) y webhook genérico
  safety.py      urgencias y bajas por reglas
  hours.py       horarios y franja de envío
  db.py          Supabase/Postgres o SQLite, mismas consultas
web/             landing, ficha de alta, dashboard admin, panel de recepción, privacidad
tests/           31 tests (lógica, HTTP, alta de clínicas)
```

## Siguiente paso

- Conectar la agenda (Google Calendar o el software de la clínica) como herramienta del agente.
- Opt-in por tecla en la llamada de Twilio ("pulsa 1 si quieres que te escribamos").
- Métricas en el panel: llamadas perdidas → mensajes → respuestas → solicitudes de cita.
