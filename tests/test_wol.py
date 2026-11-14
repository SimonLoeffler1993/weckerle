import socket

import pytest

from app import wol


def test_normalize_mac():
    assert wol.normalize_mac("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert wol.normalize_mac("aabbccddeeff") == "AA:BB:CC:DD:EE:FF"
    assert wol.normalize_mac(" AA:BB:CC:DD:EE:FF ") == "AA:BB:CC:DD:EE:FF"
    for bad in ["", "AA:BB:CC:DD:EE", "GG:BB:CC:DD:EE:FF", "AA:BB-CC:DD:EE:FF"]:
        with pytest.raises(ValueError):
            wol.normalize_mac(bad)


def test_magic_packet_format():
    p = wol.magic_packet("01:23:45:67:89:ab")
    assert len(p) == 102
    assert p[:6] == b"\xff" * 6
    assert p[6:12] == bytes.fromhex("0123456789ab")
    assert p[6:] == bytes.fromhex("0123456789ab") * 16


def test_send_magic_packet_arrives():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as rx:
        rx.bind(("127.0.0.1", 0))
        rx.settimeout(2)
        port = rx.getsockname()[1]
        wol.send_magic_packet("01:23:45:67:89:ab", "127.0.0.1", port)
        data, _ = rx.recvfrom(1024)
    assert data == wol.magic_packet("01:23:45:67:89:ab")
