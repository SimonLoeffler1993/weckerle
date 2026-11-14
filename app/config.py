"""Konfiguration über Umgebungsvariablen."""

import os
from pathlib import Path

APP_NAME = "Weckerle"
VERSION = os.getenv("WECKERLE_VERSION", "0.1.0")

# Speicherort der SQLite-Datenbank. Im Container liegt sie im Volume /data.
DATA_DIR = Path(os.getenv("WECKERLE_DATA_DIR", "./data"))
DATABASE_URL = os.getenv("WECKERLE_DATABASE_URL", f"sqlite:///{DATA_DIR / 'weckerle.db'}")
