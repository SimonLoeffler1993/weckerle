"""Datenmodelle."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import config
from app.db import Base


def local_now() -> datetime:
    """Aktuelle Uhrzeit in der eingestellten Zeitzone (ohne tzinfo, für SQLite)."""
    try:
        tz = ZoneInfo(config.TIMEZONE)
    except Exception:  # noqa: BLE001
        tz = ZoneInfo("Europe/Berlin")
    return datetime.now(tz).replace(tzinfo=None)

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAY_LABELS = {"mon": "Mo", "tue": "Di", "wed": "Mi", "thu": "Do", "fri": "Fr", "sat": "Sa", "sun": "So"}

OS_DEFAULT_SHUTDOWN = {
    "linux": "sudo -n shutdown -h now",
    "windows": "shutdown /s /t 0",
    "macos": "sudo -n shutdown -h now",
}


class Setting(Base):
    """Einfache Schlüssel-Wert-Einstellungen (z. B. Admin-Passwort-Hash)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Device(Base):
    """Ein PC, der per Wake-on-LAN eingeschaltet und per SSH ausgeschaltet wird."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    mac_address: Mapped[str] = mapped_column(String(17))
    host: Mapped[str] = mapped_column(String(255))
    broadcast_address: Mapped[str] = mapped_column(String(255), default="255.255.255.255")
    wol_port: Mapped[int] = mapped_column(Integer, default=9)
    os_type: Mapped[str] = mapped_column(String(20), default="linux")
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    ssh_user: Mapped[str] = mapped_column(String(100), default="")
    # "key" = SSH-Schlüssel der App, "password" = Passwort
    ssh_auth: Mapped[str] = mapped_column(String(20), default="key")
    ssh_password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    shutdown_command: Mapped[str] = mapped_column(String(255), default=OS_DEFAULT_SHUTDOWN["linux"])
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    schedules: Mapped[list["Schedule"]] = relationship(
        back_populates="device", cascade="all, delete-orphan", order_by="Schedule.time"
    )


class Schedule(Base):
    """Ein wiederkehrender Zeitpunkt, an dem ein Gerät ein- oder ausgeschaltet wird."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(10))  # "wake" oder "shutdown"
    time: Mapped[str] = mapped_column(String(5))  # "HH:MM"
    weekdays: Mapped[str] = mapped_column(String(40))  # z. B. "mon,tue,wed"
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    device: Mapped[Device] = relationship(back_populates="schedules")

    @property
    def weekday_list(self) -> list[str]:
        return [d for d in self.weekdays.split(",") if d]

    @property
    def weekday_text(self) -> str:
        days = self.weekday_list
        if days == WEEKDAYS:
            return "täglich"
        if days == WEEKDAYS[:5]:
            return "Mo–Fr"
        if days == WEEKDAYS[5:]:
            return "Sa, So"
        return ", ".join(WEEKDAY_LABELS[d] for d in days)


class ActionLog(Base):
    """Protokoll ausgeführter Aktionen."""

    __tablename__ = "action_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=local_now)
    device_name: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(10))
    trigger: Mapped[str] = mapped_column(String(20))  # "manuell" oder "zeitplan"
    success: Mapped[bool] = mapped_column(Boolean)
    message: Mapped[str] = mapped_column(Text, default="")
