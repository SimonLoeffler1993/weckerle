"""Einstiegspunkt der Weckerle-Web-App."""

import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app import actions, config, scheduler, security, ssh, status, wol
from app.db import get_session, init_db
from app.models import (
    COMMAND_TEMPLATES,
    OS_DEFAULT_SHUTDOWN,
    OS_LABELS,
    WEEKDAY_LABELS,
    WEEKDAYS,
    ActionLog,
    Device,
    Schedule,
    Setting,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals.update(
    app_name=config.APP_NAME,
    version=config.VERSION,
    action_labels=actions.ACTION_LABELS,
    weekday_labels=WEEKDAY_LABELS,
    weekdays=WEEKDAYS,
    os_labels=OS_LABELS,
    command_templates=COMMAND_TEMPLATES,
)

_DE_DAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _de_datetime(value) -> str:
    return f"{_DE_DAYS[value.weekday()]} {value.strftime('%d.%m. %H:%M')}"


templates.env.filters["de_dt"] = _de_datetime


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    _ensure_admin_from_env()
    ssh.app_private_key()
    if config.SCHEDULER_ENABLED:
        scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title=config.APP_NAME, version=config.VERSION, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=security.secret_key().hex(),
    session_cookie="weckerle_session",
    max_age=60 * 60 * 24 * 30,
    same_site="lax",
    https_only=config.SECURE_COOKIES,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


# --- Hilfsfunktionen ---------------------------------------------------------


def _get_setting(session: Session, key: str) -> str | None:
    row = session.get(Setting, key)
    return row.value if row else None


def _set_setting(session: Session, key: str, value: str) -> None:
    row = session.get(Setting, key)
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))
    session.commit()


def _ensure_admin_from_env() -> None:
    if not config.ADMIN_PASSWORD:
        return
    from app.db import SessionLocal

    with SessionLocal() as session:
        stored = _get_setting(session, "admin_password")
        if stored and security.verify_password(config.ADMIN_PASSWORD, stored) and (
            _get_setting(session, "admin_username") == config.ADMIN_USERNAME
        ):
            return
        _set_setting(session, "admin_username", config.ADMIN_USERNAME)
        _set_setting(session, "admin_password", security.hash_password(config.ADMIN_PASSWORD))


def flash(request: Request, message: str, kind: str = "ok") -> None:
    request.session.setdefault("flash", []).append({"kind": kind, "message": message})


def render(request: Request, name: str, **ctx) -> HTMLResponse:
    messages = request.session.pop("flash", [])
    return templates.TemplateResponse(
        request, name, {"messages": messages, "user": request.session.get("user"), **ctx}
    )


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


class RedirectTo(Exception):
    def __init__(self, url: str):
        self.url = url


@app.exception_handler(RedirectTo)
async def _redirect_to(_: Request, exc: RedirectTo):
    return redirect(exc.url)


def require_user(request: Request, session: Session = Depends(get_session)) -> str:
    if _get_setting(session, "admin_password") is None:
        raise RedirectTo("/setup")
    user = request.session.get("user")
    if not user:
        raise RedirectTo("/login")
    return user


# --- Anmeldung -------------------------------------------------------------


@app.get("/setup", response_class=HTMLResponse)
def setup_form(request: Request, session: Session = Depends(get_session)):
    if _get_setting(session, "admin_password") is not None:
        return redirect("/login")
    return render(request, "setup.html")


@app.post("/setup")
async def setup_submit(request: Request, session: Session = Depends(get_session)):
    if _get_setting(session, "admin_password") is not None:
        return redirect("/login")
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    if not username or len(password) < 8:
        flash(request, "Benutzername angeben und ein Passwort mit mindestens 8 Zeichen wählen.", "error")
        return redirect("/setup")
    if password != form.get("password2"):
        flash(request, "Die Passwörter stimmen nicht überein.", "error")
        return redirect("/setup")
    _set_setting(session, "admin_username", username)
    _set_setting(session, "admin_password", security.hash_password(password))
    request.session["user"] = username
    flash(request, "Zugang angelegt. Willkommen!")
    return redirect("/")


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, session: Session = Depends(get_session)):
    if _get_setting(session, "admin_password") is None:
        return redirect("/setup")
    return render(request, "login.html")


@app.post("/login")
async def login_submit(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    stored = _get_setting(session, "admin_password")
    if (
        stored
        and username == _get_setting(session, "admin_username")
        and security.verify_password(password, stored)
    ):
        request.session.clear()
        request.session["user"] = username
        return redirect("/")
    flash(request, "Benutzername oder Passwort falsch.", "error")
    return redirect("/login")


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/login")


# --- Übersicht ---------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_session), _: str = Depends(require_user)):
    devices = session.scalars(select(Device).order_by(Device.name)).all()
    online = status.check_many({d.id: (d.host, d.ssh_port) for d in devices})
    next_runs = {}
    for d in devices:
        runs = [(scheduler.next_run(s), s) for s in d.schedules]
        runs = [r for r in runs if r[0] is not None]
        next_runs[d.id] = min(runs, key=lambda r: r[0]) if runs else None
    recent = session.scalars(select(ActionLog).order_by(ActionLog.id.desc()).limit(8)).all()
    return render(request, "index.html", devices=devices, online=online, next_runs=next_runs, recent=recent)


@app.get("/api/status")
def api_status(session: Session = Depends(get_session), _: str = Depends(require_user)):
    devices = session.scalars(select(Device)).all()
    online = status.check_many({d.id: (d.host, d.ssh_port) for d in devices})
    return {str(k): v for k, v in online.items()}


# --- Geräte -----------------------------------------------------------------

_HOST_RE = re.compile(r"^[A-Za-z0-9.\-:\[\]_]+$")


def _device_from_form(form, device: Device) -> list[str]:
    errors = []
    device.name = str(form.get("name", "")).strip()
    if not device.name:
        errors.append("Name fehlt.")
    try:
        device.mac_address = wol.normalize_mac(str(form.get("mac_address", "")))
    except ValueError:
        errors.append("MAC-Adresse ist ungültig (Format AA:BB:CC:DD:EE:FF).")
        device.mac_address = str(form.get("mac_address", ""))
    device.host = str(form.get("host", "")).strip()
    if not device.host or not _HOST_RE.match(device.host):
        errors.append("IP-Adresse oder Hostname fehlt oder ist ungültig.")
    device.broadcast_address = str(form.get("broadcast_address", "")).strip() or "255.255.255.255"
    if not _HOST_RE.match(device.broadcast_address):
        errors.append("Broadcast-Adresse ist ungültig.")
    for field, default in (("wol_port", 9), ("ssh_port", 22)):
        raw = str(form.get(field, "")).strip() or str(default)
        try:
            value = int(raw)
            if not 1 <= value <= 65535:
                raise ValueError
            setattr(device, field, value)
        except ValueError:
            errors.append(f"Port {raw!r} ist ungültig.")
    device.os_type = str(form.get("os_type", "linux"))
    if device.os_type not in OS_DEFAULT_SHUTDOWN:
        device.os_type = "linux"
    device.ssh_user = str(form.get("ssh_user", "")).strip()
    device.ssh_auth = "password" if form.get("ssh_auth") == "password" else "key"
    new_password = str(form.get("ssh_password", ""))
    if new_password:
        device.ssh_password_enc = security.encrypt(new_password)
    if device.ssh_auth == "password" and not device.ssh_password_enc:
        errors.append("Für die Anmeldung per Passwort bitte ein SSH-Passwort angeben.")
    device.shutdown_command = (
        str(form.get("shutdown_command", "")).strip() or OS_DEFAULT_SHUTDOWN[device.os_type]
    )
    return errors


@app.get("/devices/new", response_class=HTMLResponse)
def device_new(request: Request, _: str = Depends(require_user)):
    device = Device(
        broadcast_address="255.255.255.255", wol_port=9, ssh_port=22, os_type="linux",
        ssh_auth="key", shutdown_command=OS_DEFAULT_SHUTDOWN["linux"], ssh_user="",
    )
    return render(request, "device_form.html", device=device, is_new=True, errors=[],
                  public_key=ssh.app_public_key())


@app.post("/devices/new", response_class=HTMLResponse)
async def device_create(request: Request, session: Session = Depends(get_session), _: str = Depends(require_user)):
    device = Device()
    errors = _device_from_form(await request.form(), device)
    if not errors:
        session.add(device)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            errors.append("Es gibt schon ein Gerät mit diesem Namen.")
    if errors:
        return render(request, "device_form.html", device=device, is_new=True, errors=errors,
                      public_key=ssh.app_public_key())
    flash(request, f"Gerät „{device.name}“ angelegt.")
    return redirect("/")


def _get_device(session: Session, device_id: int) -> Device:
    device = session.get(Device, device_id)
    if device is None:
        raise RedirectTo("/")
    return device


@app.get("/devices/{device_id}/edit", response_class=HTMLResponse)
def device_edit(device_id: int, request: Request, session: Session = Depends(get_session), _: str = Depends(require_user)):
    device = _get_device(session, device_id)
    return render(request, "device_form.html", device=device, is_new=False, errors=[],
                  public_key=ssh.app_public_key())


@app.post("/devices/{device_id}/edit", response_class=HTMLResponse)
async def device_update(device_id: int, request: Request, session: Session = Depends(get_session), _: str = Depends(require_user)):
    device = _get_device(session, device_id)
    errors = _device_from_form(await request.form(), device)
    if not errors:
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            errors.append("Es gibt schon ein Gerät mit diesem Namen.")
    if errors:
        session.expunge(device)
        return render(request, "device_form.html", device=device, is_new=False, errors=errors,
                      public_key=ssh.app_public_key())
    flash(request, f"Gerät „{device.name}“ gespeichert.")
    return redirect("/")


@app.post("/devices/{device_id}/delete")
def device_delete(device_id: int, request: Request, session: Session = Depends(get_session), _: str = Depends(require_user)):
    device = _get_device(session, device_id)
    session.delete(device)
    session.commit()
    scheduler.reload()
    flash(request, f"Gerät „{device.name}“ gelöscht.")
    return redirect("/")


@app.post("/devices/{device_id}/{action}")
def device_action(device_id: int, action: str, request: Request, session: Session = Depends(get_session), _: str = Depends(require_user)):
    if action not in actions.ACTION_LABELS:
        return redirect("/")
    device = _get_device(session, device_id)
    result = actions.run(session, device, action, "manuell")
    label = actions.ACTION_LABELS[action]
    flash(request, f"{label} „{device.name}“: {result.message}", "ok" if result.success else "error")
    return redirect("/")


# --- Zeitpläne --------------------------------------------------------------


@app.get("/schedules", response_class=HTMLResponse)
def schedule_list(request: Request, session: Session = Depends(get_session), _: str = Depends(require_user)):
    schedules = session.scalars(select(Schedule).join(Device).order_by(Device.name, Schedule.time)).all()
    next_runs = {s.id: scheduler.next_run(s) for s in schedules}
    has_devices = session.scalar(select(Device.id).limit(1)) is not None
    return render(request, "schedules.html", schedules=schedules, next_runs=next_runs, has_devices=has_devices)


_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _schedule_from_form(form, schedule: Schedule, session: Session) -> list[str]:
    errors = []
    try:
        schedule.device_id = int(form.get("device_id", ""))
        if session.get(Device, schedule.device_id) is None:
            raise ValueError
    except ValueError:
        errors.append("Bitte ein Gerät auswählen.")
    schedule.action = str(form.get("action", ""))
    if schedule.action not in actions.ACTION_LABELS:
        errors.append("Bitte eine Aktion auswählen.")
    schedule.time = str(form.get("time", "")).strip()[:5]
    if not _TIME_RE.match(schedule.time):
        errors.append("Uhrzeit ist ungültig (HH:MM).")
    days = [d for d in WEEKDAYS if d in form.getlist("weekdays")]
    schedule.weekdays = ",".join(days)
    if not days:
        errors.append("Mindestens einen Wochentag auswählen.")
    schedule.enabled = form.get("enabled") is not None
    return errors


def _schedule_form(request: Request, session: Session, schedule: Schedule, is_new: bool, errors: list[str]):
    devices = session.scalars(select(Device).order_by(Device.name)).all()
    return render(request, "schedule_form.html", schedule=schedule, devices=devices, is_new=is_new, errors=errors)


@app.get("/schedules/new", response_class=HTMLResponse)
def schedule_new(request: Request, session: Session = Depends(get_session), _: str = Depends(require_user)):
    device_id = request.query_params.get("device_id")
    schedule = Schedule(
        action="wake", time="07:00", weekdays=",".join(WEEKDAYS[:5]), enabled=True,
        device_id=int(device_id) if device_id and device_id.isdigit() else None,
    )
    return _schedule_form(request, session, schedule, True, [])


@app.post("/schedules/new", response_class=HTMLResponse)
async def schedule_create(request: Request, session: Session = Depends(get_session), _: str = Depends(require_user)):
    schedule = Schedule()
    errors = _schedule_from_form(await request.form(), schedule, session)
    if errors:
        return _schedule_form(request, session, schedule, True, errors)
    session.add(schedule)
    session.commit()
    scheduler.reload()
    flash(request, "Zeitplan angelegt.")
    return redirect("/schedules")


def _get_schedule(session: Session, schedule_id: int) -> Schedule:
    schedule = session.get(Schedule, schedule_id)
    if schedule is None:
        raise RedirectTo("/schedules")
    return schedule


@app.get("/schedules/{schedule_id}/edit", response_class=HTMLResponse)
def schedule_edit(schedule_id: int, request: Request, session: Session = Depends(get_session), _: str = Depends(require_user)):
    return _schedule_form(request, session, _get_schedule(session, schedule_id), False, [])


@app.post("/schedules/{schedule_id}/edit", response_class=HTMLResponse)
async def schedule_update(schedule_id: int, request: Request, session: Session = Depends(get_session), _: str = Depends(require_user)):
    schedule = _get_schedule(session, schedule_id)
    errors = _schedule_from_form(await request.form(), schedule, session)
    if errors:
        session.expunge(schedule)
        return _schedule_form(request, session, schedule, False, errors)
    session.commit()
    scheduler.reload()
    flash(request, "Zeitplan gespeichert.")
    return redirect("/schedules")


@app.post("/schedules/{schedule_id}/toggle")
def schedule_toggle(schedule_id: int, request: Request, session: Session = Depends(get_session), _: str = Depends(require_user)):
    schedule = _get_schedule(session, schedule_id)
    schedule.enabled = not schedule.enabled
    session.commit()
    scheduler.reload()
    flash(request, "Zeitplan aktiviert." if schedule.enabled else "Zeitplan pausiert.")
    return redirect("/schedules")


@app.post("/schedules/{schedule_id}/delete")
def schedule_delete(schedule_id: int, request: Request, session: Session = Depends(get_session), _: str = Depends(require_user)):
    session.delete(_get_schedule(session, schedule_id))
    session.commit()
    scheduler.reload()
    flash(request, "Zeitplan gelöscht.")
    return redirect("/schedules")


# --- Protokoll und Einstellungen -------------------------------------------


@app.get("/log", response_class=HTMLResponse)
def action_log(request: Request, session: Session = Depends(get_session), _: str = Depends(require_user)):
    entries = session.scalars(select(ActionLog).order_by(ActionLog.id.desc()).limit(200)).all()
    return render(request, "log.html", entries=entries)


@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request, _: str = Depends(require_user)):
    return render(request, "settings.html", public_key=ssh.app_public_key(), timezone=str(scheduler.timezone()))


@app.post("/settings/password")
async def change_password(request: Request, session: Session = Depends(get_session), _: str = Depends(require_user)):
    form = await request.form()
    stored = _get_setting(session, "admin_password") or ""
    if not security.verify_password(str(form.get("current", "")), stored):
        flash(request, "Aktuelles Passwort ist falsch.", "error")
    elif len(str(form.get("new", ""))) < 8:
        flash(request, "Das neue Passwort braucht mindestens 8 Zeichen.", "error")
    elif form.get("new") != form.get("new2"):
        flash(request, "Die neuen Passwörter stimmen nicht überein.", "error")
    else:
        _set_setting(session, "admin_password", security.hash_password(str(form.get("new"))))
        flash(request, "Passwort geändert.")
    return redirect("/settings")


@app.get("/health")
def health(session: Session = Depends(get_session)):
    session.execute(text("SELECT 1"))
    return {"status": "ok", "version": config.VERSION}
