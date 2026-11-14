import os
import tempfile

# Muss vor dem Import der App gesetzt werden.
os.environ["WECKERLE_DATA_DIR"] = tempfile.mkdtemp(prefix="weckerle-test-")
os.environ["WECKERLE_SCHEDULER"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

PASSWORD = "geheim123"


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    r = client.post("/setup", data={"username": "admin", "password": PASSWORD, "password2": PASSWORD})
    assert r.status_code == 200
    return client
