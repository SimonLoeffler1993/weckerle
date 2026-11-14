import pytest

from app import actions, security, ssh
from app.models import Device

from .sshserver import FakeSSHServer


@pytest.fixture
def server():
    s = FakeSSHServer(allowed_key=ssh.app_private_key())
    yield s
    s.close()


def _device(server, **kw):
    d = Device(name="pc", mac_address="AA:BB:CC:DD:EE:FF", host="127.0.0.1", ssh_port=server.port,
               ssh_user="user", ssh_auth="key", shutdown_command="sudo -n shutdown -h now")
    for k, v in kw.items():
        setattr(d, k, v)
    return d


def test_shutdown_with_app_key(server):
    result = actions.shutdown(_device(server))
    assert result.success, result.message
    assert server.commands == ["sudo -n shutdown -h now"]


def test_shutdown_with_password(server):
    d = _device(server, ssh_auth="password", ssh_password_enc=security.encrypt("pw"),
                shutdown_command="shutdown /s /t 0")
    result = actions.shutdown(d)
    assert result.success, result.message
    assert server.commands == ["shutdown /s /t 0"]


def test_shutdown_wrong_password(server):
    d = _device(server, ssh_auth="password", ssh_password_enc=security.encrypt("falsch"))
    result = actions.shutdown(d)
    assert not result.success
    assert "Anmeldung fehlgeschlagen" in result.message
    assert server.commands == []


def test_shutdown_command_fails():
    s = FakeSSHServer(allowed_key=ssh.app_private_key(), exit_code=1)
    try:
        result = actions.shutdown(_device(s))
        assert not result.success
        assert "Exit-Code 1" in result.message
    finally:
        s.close()


def test_shutdown_unreachable():
    d = Device(name="pc", mac_address="AA:BB:CC:DD:EE:FF", host="127.0.0.1", ssh_port=1,
               ssh_user="user", ssh_auth="key", shutdown_command="x")
    result = actions.shutdown(d)
    assert not result.success
    assert "Keine Verbindung" in result.message


def test_public_key_format():
    assert ssh.app_public_key().startswith("ssh-ed25519 ")
