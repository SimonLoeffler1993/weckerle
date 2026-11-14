"""Wake-on-LAN: Magic Packet senden."""

import re
import socket

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2})([:\-]?)([0-9A-Fa-f]{2})(\2[0-9A-Fa-f]{2}){4}$")


def normalize_mac(mac: str) -> str:
    """Gibt die MAC-Adresse im Format AA:BB:CC:DD:EE:FF zurück oder wirft ValueError."""
    mac = mac.strip()
    if not _MAC_RE.match(mac):
        raise ValueError(f"Ungültige MAC-Adresse: {mac!r}")
    raw = re.sub(r"[:\-]", "", mac).upper()
    return ":".join(raw[i : i + 2] for i in range(0, 12, 2))


def magic_packet(mac: str) -> bytes:
    raw = bytes.fromhex(normalize_mac(mac).replace(":", ""))
    return b"\xff" * 6 + raw * 16


def send_magic_packet(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    packet = magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))
