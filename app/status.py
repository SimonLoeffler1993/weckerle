"""Online-Status eines Geräts prüfen (TCP-Verbindung zum SSH-Port)."""

import socket
from concurrent.futures import ThreadPoolExecutor

from app import config


def is_online(host: str, port: int, timeout: float | None = None) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout or config.STATUS_TIMEOUT):
            return True
    except OSError:
        return False


def check_many(targets: dict[int, tuple[str, int]]) -> dict[int, bool]:
    if not targets:
        return {}
    with ThreadPoolExecutor(max_workers=min(16, len(targets))) as pool:
        futures = {k: pool.submit(is_online, h, p) for k, (h, p) in targets.items()}
        return {k: f.result() for k, f in futures.items()}
