"""Ausschalten per SSH und Verwaltung des SSH-Schlüssels der App."""

import io
import socket
from functools import lru_cache
from pathlib import Path

import paramiko

from app import config


def _key_path() -> Path:
    return config.DATA_DIR / "ssh" / "id_ed25519"


@lru_cache
def _load_or_create_key() -> paramiko.PKey:
    path = _key_path()
    if path.exists():
        return paramiko.Ed25519Key.from_private_key_file(str(path))
    # paramiko kann keine Ed25519-Schlüssel erzeugen, daher über cryptography.
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    pem = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.OpenSSH,
        serialization.NoEncryption(),
    )
    path.write_bytes(pem)
    path.chmod(0o600)
    return paramiko.Ed25519Key.from_private_key(io.StringIO(pem.decode()))


def app_private_key() -> paramiko.PKey:
    return _load_or_create_key()


def app_public_key() -> str:
    key = app_private_key()
    return f"{key.get_name()} {key.get_base64()} weckerle"


class SSHError(Exception):
    pass


def run_command(
    host: str,
    port: int,
    username: str,
    command: str,
    password: str | None = None,
    pkey: paramiko.PKey | None = None,
    timeout: float | None = None,
) -> str:
    """Führt einen Befehl per SSH aus und gibt die Ausgabe zurück.

    Beim Herunterfahren bricht die Verbindung oft ab, bevor ein Exit-Code kommt.
    Das wird als Erfolg gewertet.
    """
    timeout = timeout or config.SSH_TIMEOUT
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            pkey=pkey,
            timeout=timeout,
            banner_timeout=timeout,
            auth_timeout=timeout,
            look_for_keys=False,
            allow_agent=False,
        )
    except paramiko.AuthenticationException as e:
        raise SSHError("Anmeldung fehlgeschlagen (Benutzer, Passwort oder Schlüssel prüfen)") from e
    except (socket.timeout, TimeoutError) as e:
        raise SSHError(f"Keine Verbindung zu {host}:{port} (Zeitüberschreitung)") from e
    except (OSError, paramiko.SSHException) as e:
        raise SSHError(f"Keine Verbindung zu {host}:{port}: {e}") from e

    try:
        try:
            _, stdout, stderr = client.exec_command(command, timeout=timeout)
        except (socket.timeout, TimeoutError, EOFError, paramiko.SSHException):
            return "Verbindung beendet (Rechner fährt herunter)"
        try:
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode(errors="replace").strip()
            err = stderr.read().decode(errors="replace").strip()
        except (socket.timeout, TimeoutError, EOFError, paramiko.SSHException):
            return "Verbindung beendet (Rechner fährt herunter)"
        if exit_code not in (0, -1):
            raise SSHError(f"Befehl fehlgeschlagen (Exit-Code {exit_code}): {err or out}")
        return out or "Befehl ausgeführt"
    finally:
        client.close()
