import pytest
from fastapi.testclient import TestClient

from app.main import app
from conftest import CLINIC, OTHER, reset

ADMIN = {"Authorization": "Bearer admin"}

FICHA = {
    "clinica": "Clínica Dental Sol",
    "contacto": "Dra. Ruiz",
    "email": "info@dentalsol.es",
    "telefono": "600 123 456",
    "telefono_clinica": "965 000 000",
    "especialidad": "Dental",
    "direccion": "Av. Maisonnave 10, Alicante",
    "horario": {"lun": ["09:00-14:00", "16:00-20:00"], "sab": []},
    "servicios": [
        {"servicio": "Limpieza", "precio": "45 €", "nota": ""},
        {"servicio": "Ortodoncia invisible", "precio": "desde 2.400 €", "nota": "estudio gratis"},
    ],
    "faq": {"parking": "Parking público a 50 m", "seguros": "Adeslas y Sanitas", "nada": "x"},
    "instrucciones": "Trato de usted.",
    "prohibiciones": "descuentos",
    "acepta": True,
}


@pytest.fixture
def client():
    with TestClient(app) as c:
        import app.main as main
        main._hits.clear()  # el límite de envíos por IP es global al proceso
        reset(app.state.db)
        app.state.db.upsert_clinic(CLINIC)
        app.state.db.upsert_clinic(OTHER)
        yield c


def test_application_validation(client):
    assert client.post("/api/altas", json={**FICHA, "acepta": False}).status_code == 400
    assert client.post("/api/altas", json={**FICHA, "servicios": []}).status_code == 422
    bad = {**FICHA, "horario": {"lun": ["9 a 14"]}}
    assert client.post("/api/altas", json=bad).status_code == 422


def test_application_to_clinic(client):
    r = client.post("/api/altas", json=FICHA)
    assert r.status_code == 200
    app_id = r.json()["id"]

    assert client.get("/api/admin/resumen").status_code == 401
    summary = client.get("/api/admin/resumen", headers=ADMIN).json()
    ficha = summary["altas"][0]
    assert ficha["servicios"][1]["precio"] == "desde 2.400 €"
    assert "nada" not in ficha["faq"]  # solo claves conocidas

    preview = client.get(f"/api/admin/altas/{app_id}/vista-previa", headers=ADMIN).json()
    assert "- Ortodoncia invisible: desde 2.400 € (estudio gratis)" in preview["informacion"]
    assert "Seguros y mutuas: Adeslas y Sanitas" in preview["informacion"]
    assert "descuentos" in preview["instrucciones"]
    # Lo que no se rellenó se marca como desconocido (aquí: financiación sí, accesibilidad no).
    assert "Datos que NO tienes" in preview["informacion"] and "accesibilidad" in preview["informacion"]
    assert "aparcamiento" not in preview["informacion"].split("Datos que NO tienes")[1]

    r = client.post(f"/api/admin/altas/{app_id}/convertir", headers=ADMIN).json()
    assert r["clinica_id"] == "clinica-dental-sol"
    assert "WhatsApp (wa_phone_number_id)" in r["faltan"]
    assert client.post(f"/api/admin/altas/{app_id}/convertir", headers=ADMIN).status_code == 409

    clinic = app.state.db.get_clinic("clinica-dental-sol")
    assert clinic["activa"] is False
    assert clinic["numeros_llamada"] == ["+34965000000"]
    assert clinic["horario"]["lun"] == ["09:00-14:00", "16:00-20:00"]

    # No se puede activar sin WhatsApp; con él, sí.
    r = client.post("/api/admin/clinicas/clinica-dental-sol/activa", json={"activa": True}, headers=ADMIN)
    assert r.status_code == 400
    app.state.db.upsert_clinic({**clinic, "wa_phone_number_id": "PNID9"})
    r = client.post("/api/admin/clinicas/clinica-dental-sol/activa", json={"activa": True}, headers=ADMIN)
    assert r.status_code == 200
    assert app.state.db.get_clinic("clinica-dental-sol")["activa"] is True

    # Su panel funciona con el token generado.
    r = client.get("/api/panel/resumen", headers={"Authorization": f"Bearer {clinic['panel_token']}"})
    assert r.json()["clinica"] == "Clínica Dental Sol"


def test_seed_does_not_overwrite_dashboard_edits(client):
    db = app.state.db
    db.upsert_clinic({**CLINIC, "informacion": "editado en Supabase"})
    db.upsert_clinic(CLINIC, overwrite=False)
    assert db.get_clinic("c1")["informacion"] == "editado en Supabase"


def test_inactive_clinic_does_not_answer(client):
    from app import service
    from app.whatsapp import Inbound
    from conftest import FakeLLM, run
    from app.agent import Agent
    db = app.state.db
    db.set_clinic_active("c1", False)
    ev = Inbound(kind="message", phone_number_id="PNID1", phone="+34600000001", wa_id="z1", text="hola")
    assert run(service.handle_inbound(db, Agent(db, FakeLLM()), ev)) == "ignorado: clínica inactiva"


def test_simulator_on_new_inactive_clinic(client):
    from app.agent import FALLBACK_REPLY
    app_id = client.post("/api/altas", json=FICHA).json()["id"]
    cid = client.post(f"/api/admin/altas/{app_id}/convertir", headers=ADMIN).json()["clinica_id"]
    body = {"clinica_id": cid, "telefono": "600999000"}
    assert client.post("/api/dev/llamada", json=body).status_code == 401

    r = client.post("/api/dev/llamada", json=body, headers=ADMIN).json()
    assert r["resultado"] == "enviado" and "Clínica Dental Sol" in r["mensajes"][0]

    r = client.post("/api/dev/mensaje", json={**body, "texto": "me cuesta respirar"}, headers=ADMIN).json()
    assert r["resultado"] == "urgencia" and r["estado"]["solicitudes"][0]["tipo"] == "urgencia"

    client.post("/api/dev/reiniciar", json=body, headers=ADMIN)
    r = client.post("/api/dev/mensaje", json={**body, "texto": "hola"}, headers=ADMIN).json()
    # Sin GEMINI_API_KEY en los tests: respuesta de reserva y pasa a recepción.
    assert r["mensajes"] == [FALLBACK_REPLY] and r["estado"]["modo"] == "human"


def _new_clinic(client):
    app_id = client.post("/api/altas", json=FICHA).json()["id"]
    return client.post(f"/api/admin/altas/{app_id}/convertir", headers=ADMIN).json()["clinica_id"]


def test_edit_clinic_from_admin(client):
    cid = _new_clinic(client)
    data = client.get(f"/api/admin/clinicas/{cid}", headers=ADMIN).json()
    assert data["wa_token_guardado"] is None and "wa_token" not in data

    edit = {**{k: v for k, v in data.items() if k not in ("id", "activa", "wa_token_guardado")},
            "wa_phone_number_id": "123456", "wa_token": "EAAG-secreto-ABCD",
            "numeros_llamada": ["965 111 222"], "informacion": "Limpieza: 50 €"}
    r = client.put(f"/api/admin/clinicas/{cid}", json=edit, headers=ADMIN)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["wa_token_guardado"] == "…ABCD"  # nunca se devuelve entero
    clinic = app.state.db.get_clinic(cid)
    assert clinic["wa_token"] == "EAAG-secreto-ABCD"
    assert clinic["numeros_llamada"] == ["+34965111222"] and clinic["informacion"] == "Limpieza: 50 €"
    assert app.state.db.clinic_by_wa_number("123456")["id"] == cid

    # Guardar sin token mantiene el anterior; borrar_wa_token lo quita.
    client.put(f"/api/admin/clinicas/{cid}", json={**edit, "wa_token": ""}, headers=ADMIN)
    assert app.state.db.get_clinic(cid)["wa_token"] == "EAAG-secreto-ABCD"
    client.put(f"/api/admin/clinicas/{cid}", json={**edit, "borrar_wa_token": True}, headers=ADMIN)
    assert "wa_token" not in app.state.db.get_clinic(cid)

    # No se puede repetir el número de WhatsApp de otra clínica.
    r = client.put(f"/api/admin/clinicas/{cid}", json={**edit, "wa_phone_number_id": "1"}, headers=ADMIN)
    app.state.db.upsert_clinic({**CLINIC, "wa_phone_number_id": "777"})
    r = client.put(f"/api/admin/clinicas/{cid}", json={**edit, "wa_phone_number_id": "777"}, headers=ADMIN)
    assert r.status_code == 409

    # Horario mal escrito -> error claro.
    r = client.put(f"/api/admin/clinicas/{cid}", json={**edit, "horario": {"lun": ["9 a 2"]}}, headers=ADMIN)
    assert r.status_code == 400

    old = app.state.db.get_clinic(cid)["panel_token"]
    new = client.post(f"/api/admin/clinicas/{cid}/nuevo-codigo", headers=ADMIN).json()["panel_token"]
    assert new != old
    assert client.get("/api/panel/resumen", headers={"Authorization": f"Bearer {old}"}).status_code == 401


def test_per_clinic_token_and_simulator_never_sends(client, monkeypatch):
    import httpx
    from app.whatsapp import whatsapp
    from conftest import run
    sent = []

    class FakeResp:
        status_code = 200
        content = b"1"

        def json(self):
            return {"messages": [{"id": "wamid.real"}]}

    async def fake_post(self, url, headers=None, json=None):
        sent.append((url, headers["Authorization"]))
        return FakeResp()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    r = run(whatsapp.send_text("999", "+34600000000", "hola", token="TOKEN-CLINICA"))
    assert r.ok and sent[-1] == ("https://graph.facebook.com/v23.0/999/messages", "Bearer TOKEN-CLINICA")

    # El simulador nunca llama a Meta, aunque la clínica tenga token.
    cid = _new_clinic(client)
    app.state.db.upsert_clinic({**app.state.db.get_clinic(cid), "wa_phone_number_id": "999",
                                "wa_token": "TOKEN-CLINICA"})
    n = len(sent)
    body = {"clinica_id": cid, "telefono": "600123999"}
    assert client.post("/api/dev/llamada", json=body, headers=ADMIN).json()["resultado"] == "enviado"
    assert len(sent) == n


def test_demo_call_sends_real_template(client, monkeypatch):
    import httpx
    from app.config import settings
    sent = []

    class FakeResp:
        status_code = 200
        content = b"1"

        def json(self):
            return {"messages": [{"id": f"wamid.{len(sent)}"}]}

    async def fake_post(self, url, headers=None, json=None):
        sent.append(json)
        return FakeResp()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    cid = _new_clinic(client)
    body = {"telefono": "600 555 444"}
    r = client.post(f"/api/admin/clinicas/{cid}/demo-llamada", json=body, headers=ADMIN)
    assert r.status_code == 400 and "Phone number ID" in r.json()["detail"]

    clinic = app.state.db.get_clinic(cid)
    app.state.db.upsert_clinic({**clinic, "wa_phone_number_id": "555",
                                "plantilla": {"nombre": "hello_world", "idioma": "en_US", "con_nombre_clinica": False}})
    monkeypatch.setattr(settings, "wa_token", "TOKEN-GENERAL")
    for _ in range(2):  # se puede repetir la demo con el mismo móvil
        r = client.post(f"/api/admin/clinicas/{cid}/demo-llamada", json=body, headers=ADMIN).json()
        assert r["resultado"] == "enviado" and "inactiva" in r["aviso"]
    tpl = sent[-1]["template"]
    assert sent[-1]["to"] == "34600555444" and tpl["name"] == "hello_world" and "components" not in tpl
