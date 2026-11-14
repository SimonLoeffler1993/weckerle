"""Ein- und Ausschalten eines Geräts, inklusive Protokolleintrag."""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import security, ssh, wol
from app.models import ActionLog, Device

log = logging.getLogger("weckerle")

ACTION_LABELS = {"wake": "Einschalten", "shutdown": "Ausschalten"}


@dataclass
class Result:
    success: bool
    message: str


def wake(device: Device) -> Result:
    try:
        wol.send_magic_packet(device.mac_address, device.broadcast_address, device.wol_port)
    except (OSError, ValueError) as e:
        return Result(False, f"Magic Packet konnte nicht gesendet werden: {e}")
    return Result(True, f"Magic Packet an {device.mac_address} gesendet")


def shutdown(device: Device) -> Result:
    if not device.ssh_user:
        return Result(False, "Kein SSH-Benutzer hinterlegt")
    password = None
    pkey = None
    if device.ssh_auth == "password":
        password = security.decrypt(device.ssh_password_enc)
        if not password:
            return Result(False, "Kein SSH-Passwort hinterlegt")
    else:
        pkey = ssh.app_private_key()
    try:
        out = ssh.run_command(
            device.host, device.ssh_port, device.ssh_user, device.shutdown_command,
            password=password, pkey=pkey,
        )
    except ssh.SSHError as e:
        return Result(False, str(e))
    return Result(True, out)


def run(session: Session, device: Device, action: str, trigger: str) -> Result:
    if action == "wake":
        result = wake(device)
    elif action == "shutdown":
        result = shutdown(device)
    else:
        raise ValueError(f"Unbekannte Aktion: {action}")
    log.info("%s %s (%s): %s", ACTION_LABELS[action], device.name, trigger, result.message)
    session.add(
        ActionLog(
            device_name=device.name,
            action=action,
            trigger=trigger,
            success=result.success,
            message=result.message[:2000],
        )
    )
    session.commit()
    return result
