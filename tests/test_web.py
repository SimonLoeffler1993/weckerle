import socket

from app.db import SessionLocal
from app.models import ActionLog, Device, Schedule

from .conftest import PASSWORD


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_redirects_to_setup_then_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.headers["location"] == "/setup"
    client.post("/setup", data={"username": "admin", "password": PASSWORD, "password2": PASSWORD})
    client.post("/logout")
    r = client.get("/", follow_redirects=False)
    assert r.headers["location"] == "/login"
    # Setup ist nach dem ersten Mal gesperrt
    r = client.post("/setup", data={"username": "x", "password": "12345678", "password2": "12345678"}, follow_redirects=False)
    assert r.headers["location"] == "/login"


def test_login(client):
    client.post("/setup", data={"username": "admin", "password": PASSWORD, "password2": PASSWORD})
    client.post("/logout")
    r = client.post("/login", data={"username": "admin", "password": "falsch"})
    assert "falsch" in r.text
    r = client.post("/login", data={"username": "admin", "password": PASSWORD})
    assert "Geräte" in r.text
    assert "Noch keine Geräte" in r.text


def test_setup_validation(client):
    r = client.post("/setup", data={"username": "admin", "password": "kurz", "password2": "kurz"})
    assert "mindestens 8 Zeichen" in r.text


DEVICE = {
    "name": "Büro-PC", "os_type": "linux", "host": "127.0.0.1", "mac_address": "aa-bb-cc-dd-ee-ff",
    "broadcast_address": "127.0.0.1", "wol_port": "9", "ssh_user": "simon", "ssh_port": "22",
    "ssh_auth": "key", "ssh_password": "", "shutdown_command": "",
}


def test_device_crud(auth_client):
    r = auth_client.post("/devices/new", data=DEVICE)
    assert "angelegt" in r.text
    assert "Büro-PC" in r.text
    with SessionLocal() as s:
        d = s.query(Device).one()
        assert d.mac_address == "AA:BB:CC:DD:EE:FF"
        assert d.shutdown_command == "sudo -n shutdown -h now"
        device_id = d.id

    # Validierung
    r = auth_client.post("/devices/new", data={**DEVICE, "mac_address": "xyz"})
    assert "MAC-Adresse ist ungültig" in r.text
    r = auth_client.post("/devices/new", data=DEVICE)
    assert "schon ein Gerät" in r.text

    # Passwort wird verschlüsselt gespeichert
    r = auth_client.post(f"/devices/{device_id}/edit",
                         data={**DEVICE, "ssh_auth": "password", "ssh_password": "pw123", "os_type": "windows",
                               "shutdown_command": "shutdown /s /t 0"})
    assert "gespeichert" in r.text
    with SessionLocal() as s:
        d = s.get(Device, device_id)
        assert d.ssh_auth == "password"
        assert d.ssh_password_enc and "pw123" not in d.ssh_password_enc
        assert d.shutdown_command == "shutdown /s /t 0"

    # Leeres Passwort behält das gespeicherte
    auth_client.post(f"/devices/{device_id}/edit", data={**DEVICE, "ssh_auth": "password", "ssh_password": ""})
    with SessionLocal() as s:
        assert s.get(Device, device_id).ssh_password_enc

    r = auth_client.get(f"/devices/{device_id}/edit")
    assert "ssh-ed25519" in r.text

    r = auth_client.post(f"/devices/{device_id}/delete")
    assert "gelöscht" in r.text
    with SessionLocal() as s:
        assert s.query(Device).count() == 0


def test_manual_wake_sends_packet_and_logs(auth_client):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as rx:
        rx.bind(("127.0.0.1", 0))
        rx.settimeout(2)
        port = rx.getsockname()[1]
        auth_client.post("/devices/new", data={**DEVICE, "wol_port": str(port)})
        with SessionLocal() as s:
            device_id = s.query(Device).one().id
        r = auth_client.post(f"/devices/{device_id}/wake")
        data, _ = rx.recvfrom(1024)
    assert len(data) == 102
    assert "Magic Packet" in r.text
    with SessionLocal() as s:
        entry = s.query(ActionLog).one()
        assert entry.success and entry.action == "wake" and entry.trigger == "manuell"
    assert "Magic Packet" in auth_client.get("/log").text


def test_manual_shutdown_failure_is_logged(auth_client):
    auth_client.post("/devices/new", data={**DEVICE, "ssh_port": "1"})
    with SessionLocal() as s:
        device_id = s.query(Device).one().id
    r = auth_client.post(f"/devices/{device_id}/shutdown")
    assert "Keine Verbindung" in r.text
    with SessionLocal() as s:
        assert not s.query(ActionLog).one().success


def test_schedule_crud(auth_client):
    auth_client.post("/devices/new", data=DEVICE)
    with SessionLocal() as s:
        device_id = s.query(Device).one().id
    r = auth_client.get(f"/schedules/new?device_id={device_id}")
    assert r.status_code == 200
    r = auth_client.post("/schedules/new", data={
        "device_id": str(device_id), "action": "wake", "time": "07:15",
        "weekdays": ["mon", "fri"], "enabled": "on",
    })
    assert "Zeitplan angelegt" in r.text
    assert "Mo, Fr" in r.text
    with SessionLocal() as s:
        sched = s.query(Schedule).one()
        assert sched.weekdays == "mon,fri" and sched.enabled
        sid = sched.id

    r = auth_client.post("/schedules/new", data={"device_id": str(device_id), "action": "wake", "time": "25:00"})
    assert "Uhrzeit ist ungültig" in r.text
    assert "Mindestens einen Wochentag" in r.text

    r = auth_client.post(f"/schedules/{sid}/toggle")
    assert "pausiert" in r.text
    r = auth_client.post(f"/schedules/{sid}/edit", data={
        "device_id": str(device_id), "action": "shutdown", "time": "18:00",
        "weekdays": ["mon", "tue", "wed", "thu", "fri"], "enabled": "on",
    })
    assert "Mo–Fr" in r.text
    # Nächste Aktion wird auf der Übersicht angezeigt
    assert "Nächste Aktion" in auth_client.get("/").text
    r = auth_client.post(f"/schedules/{sid}/delete")
    assert "gelöscht" in r.text


def test_scheduled_execution_runs_action(auth_client):
    from app import scheduler

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as rx:
        rx.bind(("127.0.0.1", 0))
        rx.settimeout(2)
        port = rx.getsockname()[1]
        auth_client.post("/devices/new", data={**DEVICE, "wol_port": str(port)})
        with SessionLocal() as s:
            device_id = s.query(Device).one().id
        auth_client.post("/schedules/new", data={
            "device_id": str(device_id), "action": "wake", "time": "07:00", "weekdays": ["mon"], "enabled": "on",
        })
        with SessionLocal() as s:
            sid = s.query(Schedule).one().id
        scheduler.execute(sid)
        data, _ = rx.recvfrom(1024)
    assert len(data) == 102
    with SessionLocal() as s:
        assert s.query(ActionLog).one().trigger == "zeitplan"


def test_change_password(auth_client):
    r = auth_client.post("/settings/password", data={"current": "falsch", "new": "neuesPW123", "new2": "neuesPW123"})
    assert "falsch" in r.text
    r = auth_client.post("/settings/password", data={"current": PASSWORD, "new": "neuesPW123", "new2": "neuesPW123"})
    assert "Passwort geändert" in r.text
    auth_client.post("/logout")
    r = auth_client.post("/login", data={"username": "admin", "password": "neuesPW123"})
    assert "Abmelden" in r.text


def test_api_status_requires_login(client):
    r = client.get("/api/status", follow_redirects=False)
    assert r.status_code == 303


def test_device_form_command_templates(auth_client):
    r = auth_client.get("/devices/new")
    assert 'id="command_template"' in r.text
    assert "Standby" in r.text and "Herunterfahren" in r.text
    assert "sudo -n systemctl suspend" in r.text  # Vorlagen für das Skript

    # Standby-Vorlage wird gespeichert und beim Bearbeiten wieder als Vorlage erkannt
    auth_client.post("/devices/new", data={**DEVICE, "os_type": "windows",
                                           "shutdown_command": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"})
    with SessionLocal() as s:
        d = s.query(Device).one()
        assert d.shutdown_command == "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"
        device_id = d.id
    r = auth_client.get(f"/devices/{device_id}/edit")
    assert '<option value="standby" selected>' in r.text

    # Eigener Befehl bleibt erhalten und wird als „Eigener Befehl“ angezeigt
    auth_client.post(f"/devices/{device_id}/edit", data={**DEVICE, "shutdown_command": "systemctl hibernate"})
    with SessionLocal() as s:
        assert s.get(Device, device_id).shutdown_command == "systemctl hibernate"
    r = auth_client.get(f"/devices/{device_id}/edit")
    assert '<option value="custom" selected>' in r.text
