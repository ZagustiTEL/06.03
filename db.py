# db.py
# -*- coding: utf-8 -*-
"""Работа с SQLite."""
import sqlite3
import os
from flask import g, current_app


def get_db():
    if "db" not in g:
        path = current_app.config["DB_PATH"]
        g.db = sqlite3.connect(path, timeout=10, isolation_level=None)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
        g.db.execute("PRAGMA busy_timeout = 5000")
    return g.db


def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)


def tx(db):
    """Контекстный менеджер для транзакции с BEGIN IMMEDIATE.

    A06: предотвращает race condition при конкурентных списаниях.
    """
    class _Tx:
        def __enter__(self):
            db.execute("BEGIN IMMEDIATE")
            return db

        def __exit__(self, exc_type, exc, tb):
            if exc_type is None:
                db.execute("COMMIT")
            else:
                db.execute("ROLLBACK")
            return False
    return _Tx()