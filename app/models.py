"""Datenmodelle.

Schritt 1 legt nur das Gerüst an. Geräte (PCs) und Zeitpläne folgen in
Schritt 2 und 3.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Device(Base):
    """Ein PC, der per Wake-on-LAN eingeschaltet und per SSH ausgeschaltet wird."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    mac_address: Mapped[str] = mapped_column(String(17))
    host: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
