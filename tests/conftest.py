import os
import shutil
import tempfile

# Must be set BEFORE the app is imported: settings/engine are created at import time.
_tmp = tempfile.mkdtemp(prefix="shop-tests-")
os.environ.update(
    DATABASE_URL=f"sqlite:///{_tmp}/test.db",
    JWT_SECRET="test-secret",
    LLM_PROVIDER="mock",
    BCRYPT_ROUNDS="4",
    UPLOAD_DIR=f"{_tmp}/uploads",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.seed import seed  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

CUSTOMER = ("customer@demo.com", "Customer123!")
SELLER = ("seller@demo.com", "Seller123!")
SELLER2 = ("seller2@demo.com", "Seller123!")


_DB_FILE = f"{_tmp}/test.db"
_TEMPLATE = f"{_tmp}/template.db"


@pytest.fixture(scope="session", autouse=True)
def _seed_template():
    seed(reset=True)
    engine.dispose()
    shutil.copy(_DB_FILE, _TEMPLATE)


@pytest.fixture(autouse=True)
def fresh_db():
    """Every test starts from the same seeded database (restored from a template copy: fast)."""
    engine.dispose()
    shutil.copy(_TEMPLATE, _DB_FILE)
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


def login(client, creds) -> dict:
    r = client.post("/api/auth/login", json={"email": creds[0], "password": creds[1]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def customer(client):
    return login(client, CUSTOMER)


@pytest.fixture
def seller(client):
    return login(client, SELLER)


@pytest.fixture
def seller2(client):
    return login(client, SELLER2)


@pytest.fixture
def seller3(client):
    """Owns the kitchen appliances (VoltBrew kettle, blender...) in the seed data."""
    return login(client, ("seller3@demo.com", "Seller123!"))


def find_product(client, title_part: str) -> dict:
    r = client.get("/api/products", params={"q": title_part})
    assert r.status_code == 200 and r.json()["items"], f"no product matching {title_part}"
    return r.json()["items"][0]


ADDRESS = {"full_name": "Test Buyer", "phone": "03001234567", "line1": "1 Test Street", "city": "Lahore", "postal_code": "54000"}
