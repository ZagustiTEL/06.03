# backups.py
# -*- coding: utf-8 -*-
"""Бэкапы с HMAC-подписью, ротацией и защитой от path traversal."""
import os
import hmac
import hashlib
import shutil
import sqlite3
import datetime

from flask import current_app

from validators import safe_backup_name, ValidationError


def _paths():
    return current_app.config["DB_PATH"], current_app.config["BACKUP_DIR"]


def _hmac_key():
    key = current_app.config.get("BACKUP_HMAC_KEY") or current_app.config["SECRET_KEY"]
    if isinstance(key, str):
        key = key.encode("utf-8")
    return key


def _sign_file(path):
    """Возвращает hex-подпись файла."""
    h = hmac.new(_hmac_key(), digestmod=hashlib.sha256)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_signature(backup_path, sig):
    with open(backup_path + ".sig", "w", encoding="utf-8") as f:
        f.write(sig)


def _read_signature(backup_path):
    sig_path = backup_path + ".sig"
    if not os.path.exists(sig_path):
        return None
    with open(sig_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def make_backup():
    """Создаёт бэкап БД, подписывает HMAC, ротирует старые."""
    db_path, backup_dir = _paths()
    if not os.path.exists(db_path):
        return None
    os.makedirs(backup_dir, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dst = os.path.join(backup_dir, f"sklad_{ts}.db")

    # A06: используем SQLite backup API вместо copy2, чтобы получить консистентный снимок
    src = sqlite3.connect(db_path)
    try:
        dst_conn = sqlite3.connect(dst)
        try:
            src.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src.close()

    sig = _sign_file(dst)
    _write_signature(dst, sig)

    rotate_backups()
    return dst


def rotate_backups():
    """A06: не более MAX_BACKUPS файлов .db (и их .sig)."""
    _, backup_dir = _paths()
    if not os.path.isdir(backup_dir):
        return
    max_n = current_app.config["MAX_BACKUPS"]
    files = sorted(
        (f for f in os.listdir(backup_dir) if f.endswith(".db")),
        reverse=True,
    )
    for old in files[max_n:]:
        for p in (os.path.join(backup_dir, old), os.path.join(backup_dir, old + ".sig")):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


def daily_backup_if_needed():
    _, backup_dir = _paths()
    today = datetime.date.today().strftime("%Y%m%d")
    if os.path.isdir(backup_dir):
        for f in os.listdir(backup_dir):
            if f.startswith(f"sklad_{today}"):
                return
    make_backup()


def list_backups():
    _, backup_dir = _paths()
    items = []
    if not os.path.isdir(backup_dir):
        return items
    for f in sorted(
        (x for x in os.listdir(backup_dir) if x.endswith(".db")),
        reverse=True,
    ):
        path = os.path.join(backup_dir, f)
        st = os.stat(path)
        items.append({
            "name": f,
            "size": round(st.st_size / 1024, 1),
            "mtime": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "signed": _read_signature(path) is not None,
        })
    return items


def restore_backup(name):
    """A01/A08: безопасное восстановление с проверкой имени и подписи."""
    db_path, backup_dir = _paths()

    try:
        safe_name = safe_backup_name(name)
    except ValidationError:
        return False, "Недопустимое имя файла."

    src = os.path.join(backup_dir, safe_name)
    # Финальная проверка: путь действительно внутри backup_dir
    real_src = os.path.realpath(src)
    real_dir = os.path.realpath(backup_dir)
    if os.path.commonpath([real_src, real_dir]) != real_dir:
        return False, "Недопустимый путь."
    if not os.path.isfile(real_src):
        return False, "Файл бэкапа не найден."

    # A08: проверка HMAC
    expected = _read_signature(real_src)
    if expected is None:
        return False, "У файла бэкапа отсутствует подпись — восстановление запрещено."
    actual = _sign_file(real_src)
    if not hmac.compare_digest(expected, actual):
        return False, "Подпись бэкапа не совпадает — файл повреждён или подменён."

    # Проверяем, что это действительно SQLite с ожидаемой схемой
    try:
        check = sqlite3.connect(real_src)
        try:
            tables = {r[0] for r in check.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        finally:
            check.close()
    except sqlite3.DatabaseError:
        return False, "Файл не является корректной БД SQLite."

    required = {"users", "products", "receipts", "shipments", "writeoffs"}
    if not required.issubset(tables):
        return False, "Бэкап не содержит ожидаемых таблиц."

    # Страховочный бэкап текущего состояния
    make_backup()
    shutil.copy2(real_src, db_path)
    return True, "База данных восстановлена."