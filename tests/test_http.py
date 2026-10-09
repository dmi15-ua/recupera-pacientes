import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from conftest import CLINIC, OTHER


@pytest.fixture
def client():
    with TestClient(app) as c:
        from conftest import reset
        reset(app.state.db)
        app.state.db.upsert_clinic(CLINIC)
        app.state.db.upsert_clinic(OTHER)
        yield c


def wa_sign(raw: bytes) -> str:
    return "sha256=" + hmac.new(b"secreto-app", raw, hashlib.sha256).hexdigest()


def twilio_sign(url, params):
    data = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(hmac.new(b"twilio-token", data.encode(), hashlib.sha1).digest()).decode()


def test_whatsapp_verify(client):
    r = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verificame",
                                                  "hub.challenge": "123"})
    assert r.text == "123"
    r = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "mal",
                                                  "hub.challenge": "123"})
    assert r.status_code == 403


def test_whatsapp_webhook_requires_signature(client):
    body = {"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "PNID1"},
        "contacts": [{"wa_id": "34600999888", "profile": {"name": "Eva"}}],
        "messages": [{"from": "34600999888", "id": "wamid.1", "type": "text", "text": {"body": "hola"}}],
    }}]}]}
    raw = json.dumps(body).encode()
    assert client.post("/webhooks/whatsapp", content=raw).status_code == 401
    assert client.post("/webhooks/whatsapp", content=raw,
                       headers={"X-Hub-Signature-256": "sha256=00"}).status_code == 401
    r = client.post("/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": wa_sign(raw)})
    assert r.status_code == 200
    conv = app.state.db.open_conversation("c1", "+34600999888")
    assert conv["name"] == "Eva" and conv["reply_due_at"]


def test_generic_call_webhook(client):
    payload = {"to": "910000000", "from": "600555444", "id": "abc"}
    assert client.post("/webhooks/llamada", json=payload).status_code == 401
    r = client.post("/webhooks/llamada", json=payload, headers={"X-Webhook-Token": "token-centralita"})
    assert r.json() == {"resultado": "registrada"}
    r = client.post("/webhooks/llamada", json={**payload, "to": "+34999999999"},
                    headers={"X-Webhook-Token": "token-centralita"})
    assert r.status_code == 404


def test_twilio_dial_flow(client):
    url = "https://test.local/webhooks/twilio/fin"
    params = {"From": "+34600777666", "To": "+34910000000", "CallSid": "CA1", "DialCallStatus": "no-answer"}
    r = client.post("/webhooks/twilio/fin", data=params, headers={"X-Twilio-Signature": "falsa"})
    assert r.status_code == 401
    r = client.post("/webhooks/twilio/fin", data=params, headers={"X-Twilio-Signature": twilio_sign(url, params)})
    assert r.status_code == 200 and "WhatsApp" in r.text
    row = app.state.db._one("SELECT * FROM {T}missed_calls WHERE call_ref = 'CA1'")
    assert row["phone"] == "+34600777666" and row["clinic_id"] == "c1"


def test_twilio_voice_dials_reception(client):
    url = "https://test.local/webhooks/twilio/voz"
    params = {"From": "+34600777666", "To": "+34910000000", "CallSid": "CA2"}
    r = client.post("/webhooks/twilio/voz", data=params, headers={"X-Twilio-Signature": twilio_sign(url, params)})
    assert "<Dial" in r.text and "+34910000001" in r.text


def test_lead_form(client):
    base = {"clinica": "Clínica X", "telefono": "600123123", "acepta": True}
    assert client.post("/api/leads", json={**base, "acepta": False}).status_code == 400
    assert client.post("/api/leads", json=base).json() == {"ok": True}
    assert client.post("/api/leads", json={**base, "web": "http://spam"}).json() == {"ok": True}
    assert app.state.db._one("SELECT COUNT(*) n FROM {T}leads")["n"] == 1


def test_panel_isolated_per_clinic(client):
    db = app.state.db
    conv = db.get_or_open_conversation("c1", "+34600111000", "whatsapp")
    assert client.get("/api/panel/resumen").status_code == 401
    r = client.get("/api/panel/resumen", headers={"Authorization": "Bearer panel-c1"})
    assert r.json()["clinica"] == "Clínica Prueba"
    other = client.get(f"/api/panel/conversaciones/{conv['id']}", headers={"Authorization": "Bearer panel-c2"})
    assert other.status_code == 404


def test_panel_reply_respects_24h_window(client):
    db = app.state.db
    conv = db.get_or_open_conversation("c1", "+34600111001", "llamada_perdida")
    h = {"Authorization": "Bearer panel-c1"}
    r = client.post(f"/api/panel/conversaciones/{conv['id']}/responder", json={"texto": "hola"}, headers=h)
    assert r.status_code == 409
    db.update_conversation(conv["id"], last_patient_at=int(time.time()))
    r = client.post(f"/api/panel/conversaciones/{conv['id']}/responder", json={"texto": "hola"}, headers=h)
    assert r.status_code == 200
    assert db.get_conversation(conv["id"])["mode"] == "human"


def test_dev_simulator_requires_admin(client):
    body = {"clinica_id": "c1", "telefono": "600123456", "texto": "hola"}
    assert client.post("/api/dev/mensaje", json=body).status_code == 401
    r = client.post("/api/dev/mensaje", json=body, headers={"Authorization": "Bearer admin"})
    assert r.status_code == 200


def test_panel_funnel(client):
    db = app.state.db
    now = int(time.time())
    for i in range(3):
        call_id = db.add_missed_call("c1", f"+3460022200{i}", f"f{i}", now)
        if i < 2:
            db.set_missed_status(call_id, "enviado")
    conv = db.get_or_open_conversation("c1", "+34600222000", "llamada_perdida")
    db.add_message(conv["id"], "patient", "hola")
    db.add_request("c1", conv["id"], "cita", "+34600222000")
    db.get_or_open_conversation("c1", "+34600222001", "llamada_perdida")  # sin respuesta
    r = client.get("/api/panel/resumen", headers={"Authorization": "Bearer panel-c1"})
    f = r.json()["embudo_30d"]
    assert f["perdidas"] == 3 and f["enviados"] == 2 and f["respondieron"] == 1 and f["citas"] == 1
    assert client.get("/api/panel/resumen", headers={"Authorization": "Bearer panel-c2"}).json()["embudo_30d"]["perdidas"] == 0


def test_health_muestra_el_commit(client, monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "4c246740d844b4d756fc17d39d6b34c5d5861d28")
    assert client.get("/salud").json() == {"ok": True, "commit": "4c24674"}
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA")
    assert client.get("/salud").json() == {"ok": True, "commit": None}
