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
| Servidor | Un VPS pequeño (unos 4–5 €/mes) o el nivel gratuito de Oracle Cloud. SQLite, sin base de datos aparte. |
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
- Panel de recepción: <http://localhost:8000/panel> (código: el `panel_token` de `clinicas.json`)

Tests:

```bash
python -m pytest -q
```

## Poner en producción

1. **Servidor**: despliega el `Dockerfile` con un volumen en `/app/data`. Copia ahí `clinicas.json`
   y pon `CLINICS_FILE=/app/data/clinicas.json`. Un solo proceso (no uses `--workers`).
2. **Gemini**: crea una API key en un proyecto de Google Cloud con facturación → `GEMINI_API_KEY`.
3. **WhatsApp (Meta)**:
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
4. **Llamadas**, una de dos:
   - **Centralita con webhooks**: que haga `POST https://tu-dominio/webhooks/llamada` con la cabecera
     `X-Webhook-Token: <CALL_WEBHOOK_TOKEN>` y el cuerpo
     `{"to": "+34910000000", "from": "+34600111222", "id": "id-unico", "estado": "perdida"}`
     (o `"atendida"` para cancelar el mensaje si luego le cogen).
   - **Twilio**: compra un número, apunta su *Voice webhook* a `https://tu-dominio/webhooks/twilio/voz`,
     pon `TWILIO_AUTH_TOKEN` y en la clínica `numeros_llamada` (el de Twilio) y `telefono_recepcion`
     (al que se pasa la llamada). Twilio hace sonar recepción y, si nadie coge, avisa al paciente
     de que le escribirán por WhatsApp.
5. **Avisos**: crea un bot con @BotFather → `TELEGRAM_BOT_TOKEN`. Añádelo al grupo de recepción y pon
   el id del grupo en `telegram_chat_id` de la clínica. `OWNER_TELEGRAM_CHAT_ID` recibe los leads de la landing.
6. **Privacidad**: completa `web/privacidad.html` y firma el contrato de encargado del tratamiento
   con cada clínica.

## Estructura

```
app/
  main.py        rutas: webhooks, panel, leads, simulador
  service.py     reglas: llamadas perdidas, mensajes entrantes, bucle de tareas
  agent.py       prompt + herramientas del asistente
  llm.py         cliente de Gemini (function calling)
  whatsapp.py    WhatsApp Cloud API: envío, firma y parseo de webhooks
  telephony.py   Twilio (firma, TwiML) y webhook genérico
  safety.py      urgencias y bajas por reglas
  hours.py       horarios y franja de envío
  db.py          SQLite
web/             landing, panel de recepción, privacidad
tests/           27 tests (lógica + HTTP)
```

## Siguiente paso

- Conectar la agenda (Google Calendar o el software de la clínica) como herramienta del agente.
- Opt-in por tecla en la llamada de Twilio ("pulsa 1 si quieres que te escribamos").
- Métricas en el panel: llamadas perdidas → mensajes → respuestas → solicitudes de cita.
