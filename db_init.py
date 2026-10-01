# db_init.py
# -*- coding: utf-8 -*-
"""Инициализация БД."""
import os
import sqlite3
import secrets
from werkzeug.security import generate_password_hash

from config import Config


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','storekeeper','operator','manager')),
    failed_attempts INTEGER DEFAULT 0,
    is_blocked INTEGER DEFAULT 0,
    must_change_password INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    unit TEXT DEFAULT 'шт',
    price REAL DEFAULT 0 CHECK(price >= 0),
    quantity INTEGER DEFAULT 0 CHECK(quantity >= 0),
    min_quantity INTEGER DEFAULT 0 CHECK(min_quantity >= 0),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    supplier TEXT,
    comment TEXT,
    user_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(product_id) REFERENCES products(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS shipments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    destination TEXT,
    comment TEXT,
    user_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(product_id) REFERENCES products(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS writeoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    reason TEXT,
    user_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(product_id) REFERENCES products(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    manager_id INTEGER,
    full_name TEXT NOT NULL,
    position TEXT,
    salary REAL DEFAULT 0 CHECK(salary >= 0),
    hired_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(manager_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    work_date TEXT NOT NULL,
    hours REAL DEFAULT 8 CHECK(hours > 0 AND hours <= 12),
    note TEXT,
    FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS payroll (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    period TEXT NOT NULL,
    hours REAL DEFAULT 0,
    amount REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS finance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK(kind IN ('income','expense')),
    amount REAL NOT NULL CHECK(amount > 0),
    description TEXT,
    user_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    details TEXT,
    ip TEXT,
    ua TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    ip TEXT NOT NULL,
    ts INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_receipts_product   ON receipts(product_id);
CREATE INDEX IF NOT EXISTS idx_receipts_created   ON receipts(created_at);
CREATE INDEX IF NOT EXISTS idx_shipments_product  ON shipments(product_id);
CREATE INDEX IF NOT EXISTS idx_shipments_created  ON shipments(created_at);
CREATE INDEX IF NOT EXISTS idx_writeoffs_product  ON writeoffs(product_id);
CREATE INDEX IF NOT EXISTS idx_writeoffs_created  ON writeoffs(created_at);
CREATE INDEX IF NOT EXISTS idx_finance_kind_cr    ON finance(kind, created_at);
CREATE INDEX IF NOT EXISTS idx_finance_created    ON finance(created_at);
CREATE INDEX IF NOT EXISTS idx_shifts_emp_date    ON shifts(employee_id, work_date);
CREATE INDEX IF NOT EXISTS idx_payroll_emp_period ON payroll(employee_id, period);
CREATE INDEX IF NOT EXISTS idx_audit_created      ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_products_lowstock  ON products(quantity, min_quantity);
CREATE INDEX IF NOT EXISTS idx_employees_manager  ON employees(manager_id);
CREATE INDEX IF NOT EXISTS idx_login_attempts     ON login_attempts(username, ip, ts);
"""


def _connect(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def migrate(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "must_change_password" not in cols:
        conn.execute(
            "ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0"
        )
    audit_cols = {r[1] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()}
    if "ip" not in audit_cols:
        conn.execute("ALTER TABLE audit_log ADD COLUMN ip TEXT")
    if "ua" not in audit_cols:
        conn.execute("ALTER TABLE audit_log ADD COLUMN ua TEXT")
    conn.commit()


def seed_demo(conn):
    """A02: вместо хардкода — случайный пароль, выводится один раз в stdout."""
    cur = conn.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] > 0:
        return

    admin_pwd = os.environ.get("SKLAD_ADMIN_PASSWORD") or "ChangeMe_" + secrets.token_urlsafe(8)
    conn.execute(
        "INSERT INTO users(username, password_hash, full_name, role, must_change_password) "
        "VALUES (?,?,?,?,1)",
        ("admin", generate_password_hash(admin_pwd, method="scrypt"),
         "Администратор", "admin"),
    )
    print("=" * 60)
    print(f"[db_init] Создан администратор: admin / {admin_pwd}")
    print("[db_init] Смените пароль после первого входа!")
    print("=" * 60)

    products = [
        ("SKU-001", "Болт М8", "шт", 5.5, 1000, 100),
        ("SKU-002", "Гайка М8", "шт", 3.0, 1500, 100),
        ("SKU-003", "Шайба 8", "шт", 1.2, 2000, 200),
        ("SKU-004", "Кабель UTP cat5e (м)", "м", 25.0, 500, 50),
        ("SKU-005", "Розетка RJ-45", "шт", 120.0, 80, 20),
    ]
    for sku, name, unit, price, qty, minq in products:
        conn.execute(
            "INSERT INTO products(sku, name, unit, price, quantity, min_quantity) "
            "VALUES (?,?,?,?,?,?)",
            (sku, name, unit, price, qty, minq),
        )
    conn.commit()


def init_db(force=False):
    path = Config.DB_PATH
    if force and os.path.exists(path):
        os.remove(path)
    conn = _connect(path)
    try:
        create_schema(conn)
        migrate(conn)
        seed_demo(conn)
    finally:
        conn.close()
    print(f"[db_init] База данных готова: {path}")


if __name__ == "__main__":
    init_db(force=False)