from app import security


def test_password_hash():
    h = security.hash_password("abc12345")
    assert security.verify_password("abc12345", h)
    assert not security.verify_password("falsch", h)
    assert not security.verify_password("abc12345", "kaputt")


def test_encrypt_roundtrip():
    token = security.encrypt("geheim")
    assert token != "geheim"
    assert security.decrypt(token) == "geheim"
    assert security.decrypt("kaputt") is None
    assert security.decrypt(None) is None
