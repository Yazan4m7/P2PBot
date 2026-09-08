import os
from pathlib import Path

TEST_DB = Path('/tmp/p2psim_test.sqlite3')
try:
    TEST_DB.unlink()
except FileNotFoundError:
    pass
os.environ["P2PSIM_DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["P2PSIM_AUTH_REQUIRED"] = "true"

import pytest
from fastapi.testclient import TestClient

from p2psim.api import app, engine


@pytest.fixture(autouse=True)
def clean_simulation():
    engine.reset(seed=12345)
    yield


@pytest.fixture
def client():
    return TestClient(app)
