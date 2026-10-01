# tests/test_security.py
# -*- coding: utf-8 -*-
"""Тесты RBAC и HMAC-подписи бэкапов."""
import os
import tempfile

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests-only")

from app import create_app
from config import Config
from db import get_db


@pytest.fixture
def app(tmp_path):
    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = "test-secret-key"
        DB_PATH = str(tmp_path / "test.db")
        BACKUP_DIR = str(tmp_path / "backups")
        WTF_CSRF_ENABLED = False
        SESSION_COOKIE_SECURE = False
        DEBUG = False

    application = create_app(TestConfig)

    with application.app_context():
        from db_init import create_schema, migrate
        from security import hash_password
        db = get_db()
        create_schema(db)
        migrate(db)
        db.execute(
            "INSERT INTO users(username, password_hash, full_name, role, "
            "must_change_password, is_blocked) VALUES (?,?,?,?,0,0)",
            ("admin1", hash_password("AdminPass123"), "Админ", "admin"),
        )
        db.execute(
            "INSERT INTO users(username, password_hash, full_name, role, "
            "must_change_password, is_blocked) VALUES (?,?,?,?,0,0)",
            ("manager1", hash_password("ManagerPass123"), "Менеджер", "manager"),
        )
        db.execute(
            "INSERT INTO products(sku, name, unit, price, quantity, min_quantity) "
            "VALUES ('T-1', 'Тест', 'шт', 100, 10, 1)"
        )
        db.commit()

    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def test_manager_cannot_access_stock(client):
    """RBAC: manager на /receipts, /shipments, /writeoffs → 403."""
    _login(client, "manager1", "ManagerPass123")
    for url in ("/receipts", "/shipments", "/writeoffs"):
        r = client.get(url)
        assert r.status_code == 403, f"manager получил доступ к {url}"


def test_manager_cannot_post_receipt(client):
    """RBAC: manager не может даже POST-ом провести приём."""
    _login(client, "manager1", "ManagerPass123")
    r = client.post("/receipts", data={
        "product_id": 1, "quantity": 5, "supplier": "X", "comment": "",
    })
    assert r.status_code == 403


def test_manager_sees_only_own_finance(client, app):
    """Финансы: manager видит только свои операции."""
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO finance(kind, amount, description, user_id) "
            "VALUES ('income', 1000, 'свой', 2)"
        )
        db.execute(
            "INSERT INTO finance(kind, amount, description, user_id) "
            "VALUES ('income', 9999, 'чужой', 1)"
        )
        db.commit()

    _login(client, "manager1", "ManagerPass123")
    r = client.get("/finance")
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "свой" in body
    assert "чужой" not in body


def test_must_change_password_redirect(client, app):
    """must_change_password=1 → редирект на /change-password."""
    with app.app_context():
        db = get_db()
        db.execute("UPDATE users SET must_change_password=1 WHERE username='manager1'")
        db.commit()

    _login(client, "manager1", "ManagerPass123")
    r = client.get("/products", follow_redirects=False)
    assert r.status_code == 302
    assert "/change-password" in r.headers["Location"]


def test_product_delete_with_fk_conflict(client, app):
    """Удаление товара с историей приёмок → без 500, сообщение об ошибке."""
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO receipts(product_id, quantity, supplier, user_id) "
            "VALUES (1, 1, 'X', 1)"
        )
        db.commit()

    _login(client, "admin1", "AdminPass123")
    r = client.post("/products/delete/1", follow_redirects=True)
    assert r.status_code == 200
    assert "Невозможно удалить" in r.get_data(as_text=True)


def test_backup_hmac_rejects_tampered_file(client, app):
    """A08: подделка бэкапа → отказ восстановления."""
    _login(client, "admin1", "AdminPass123")

    # Создаём бэкап
    r = client.post("/backups/create", follow_redirects=True)
    assert r.status_code == 200

    with app.app_context():
        backup_dir = app.config["BACKUP_DIR"]
        files = [f for f in os.listdir(backup_dir) if f.endswith(".db")]
        assert files, "бэкап не создан"
        victim = files[0]
        path = os.path.join(backup_dir, victim)

        # Подменяем содержимое — HMAC должен не совпасть
        with open(path, "ab") as f:
            f.write(b"\x00tampered")

    r = client.post("/backups/restore", data={"name": victim}, follow_redirects=True)
    body = r.get_data(as_text=True)
    assert "Подпись" in body or "подпис" in body.lower()
    assert "повреждён" in body or "подменён" in body


def test_logout_get_not_allowed(client):
    """Logout доступен только по POST."""
    r = client.get("/logout")
    assert r.status_code == 405