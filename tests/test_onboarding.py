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
