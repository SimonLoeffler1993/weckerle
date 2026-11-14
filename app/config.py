"""Konfiguration über Umgebungsvariablen."""

import os
from pathlib import Path

APP_NAME = "Weckerle"
VERSION = os.getenv("WECKERLE_VERSION", "1.0.0")

# Datenordner: SQLite-Datenbank, geheimer Schlüssel und SSH-Schlüssel der App.
DATA_DIR = Path(os.getenv("WECKERLE_DATA_DIR", "./data"))
DATABASE_URL = os.getenv("WECKERLE_DATABASE_URL", f"sqlite:///{DATA_DIR / 'weckerle.db'}")

# Zeitzone für die Zeitpläne.
TIMEZONE = os.getenv("TZ", "Europe/Berlin")

# Optional: Admin-Zugang vorgeben, statt ihn beim ersten Aufruf anzulegen.
ADMIN_USERNAME = os.getenv("WECKERLE_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("WECKERLE_ADMIN_PASSWORD")

# Scheduler abschalten (z. B. für Tests).
SCHEDULER_ENABLED = os.getenv("WECKERLE_SCHEDULER", "1") not in ("0", "false", "no")

# Session-Cookie nur über HTTPS senden (hinter einem Reverse-Proxy mit TLS sinnvoll).
SECURE_COOKIES = os.getenv("WECKERLE_SECURE_COOKIES", "0") in ("1", "true", "yes")

# Timeouts in Sekunden
SSH_TIMEOUT = float(os.getenv("WECKERLE_SSH_TIMEOUT", "10"))
STATUS_TIMEOUT = float(os.getenv("WECKERLE_STATUS_TIMEOUT", "1.0"))
