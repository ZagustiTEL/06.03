# tests/test_app.py
import os
import tempfile
import pytest

# Config требует SECRET_KEY ещё на этапе импорта,
# поэтому задаём переменные окружения до импорта приложения.
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault(
    "SKLAD_DB_PATH",
    os.path.join(tempfile.gettempdir(), "sklad_test_global.db"),
)
os.environ.setdefault(
    "SKLAD_BACKUP_DIR",
    os.path.join(tempfile.gettempdir(), "sklad_test_backups"),
)

from app import create_app
from config import Config
from db import get_db
from db_init import create_schema, migrate
from security import hash_password
from validators import safe_backup_name, sanitize_cell, ValidationError


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key"


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "test_sklad.db"
    backup_dir = tmp_path / "backups"

    class Cfg(TestConfig):
        pass

    Cfg.DB_PATH = str(db_path)
    Cfg.BACKUP_DIR = str(backup_dir)
    Cfg.BACKUP_HMAC_KEY = "test-hmac-key"

    app = create_app(Cfg)

    with app.app_context():
        db = get_db()
        create_schema(db)
        migrate(db)
        db.execute(
            "INSERT INTO users(username, password_hash, full_name, role, must_change_password) "
            "VALUES (?,?,?,?,?)",
            ("admin", hash_password("Admin_12345"), "Администратор", "admin", 0),
        )
        db.commit()

    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, username="admin", password="Admin_12345"):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


def test_index_requires_login(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_admin_can_login(client):
    resp = login(client)
    assert resp.status_code == 200
    assert "Панель управления" in resp.get_data(as_text=True)


def test_receipt_increases_product_quantity(app, client):
    login(client)

    resp = client.post(
        "/products/add",
        data={
            "sku": "TEST-001",
            "name": "Тестовый товар",
            "unit": "шт",
            "price": "10.50",
            "quantity": "0",
            "min_quantity": "1",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        db = get_db()
        row = db.execute(
            "SELECT id, quantity FROM products WHERE sku=?",
            ("TEST-001",),
        ).fetchone()
        assert row is not None
        pid = row["id"]
        assert row["quantity"] == 0

    resp = client.post(
        "/receipts",
        data={
            "product_id": str(pid),
            "quantity": "5",
            "supplier": "ООО Тест",
            "comment": "",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Товар принят на склад" in resp.get_data(as_text=True)

    with app.app_context():
        db = get_db()
        row = db.execute(
            "SELECT quantity FROM products WHERE id=?",
            (pid,),
        ).fetchone()
        assert row["quantity"] == 5

        cnt = db.execute(
            "SELECT COUNT(*) FROM receipts WHERE product_id=?",
            (pid,),
        ).fetchone()[0]
        assert cnt == 1


def test_safe_backup_name_rejects_path_traversal():
    with pytest.raises(ValidationError):
        safe_backup_name("../sklad.db")

    with pytest.raises(ValidationError):
        safe_backup_name("subdir/sklad.db")

    assert safe_backup_name("sklad_20240101_120000.db") == "sklad_20240101_120000.db"


def test_sanitize_cell_escapes_formula_injection():
    assert sanitize_cell("=1+1") == "'=1+1"
    assert sanitize_cell("+79990000000") == "'+79990000000"
    assert sanitize_cell("обычный текст") == "обычный текст"