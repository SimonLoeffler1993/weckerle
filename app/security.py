"""Geheimer Schlüssel, Verschlüsselung der SSH-Passwörter und Passwort-Hashing."""

import base64
import hashlib
import hmac
import os
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app import config


@lru_cache
def secret_key() -> bytes:
    """Lädt den geheimen Schlüssel aus dem Datenordner oder erzeugt ihn beim ersten Start."""
    env = os.getenv("WECKERLE_SECRET_KEY")
    if env:
        return hashlib.sha256(env.encode()).digest()
    path = config.DATA_DIR / "secret.key"
    if path.exists():
        return base64.urlsafe_b64decode(path.read_bytes().strip())
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    path.write_bytes(base64.urlsafe_b64encode(key))
    path.chmod(0o600)
    return key


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(secret_key()))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(digest.hex(), digest_hex)
