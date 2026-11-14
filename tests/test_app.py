import os
import tempfile

os.environ["WECKERLE_DATA_DIR"] = tempfile.mkdtemp()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_health():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_index():
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "Weckerle" in r.text
