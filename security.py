# security.py
# -*- coding: utf-8 -*-
"""Аутентификация, авторизация, CSRF, rate limiting."""
import time
import hmac
from functools import wraps

from flask import (
    session, redirect, url_for, flash, request, g, current_app, abort
)
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_db

csrf = CSRFProtect()

# A07: dummy-hash для защиты от user enumeration по timing
_DUMMY_HASH = generate_password_hash("dummy-password-for-timing")


def init_app(app):
    csrf.init_app(app)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        flash("Запрос отклонён: недействительный CSRF-токен. Обновите страницу.", "error")
        return redirect(url_for("auth.login")), 400


def hash_password(pwd):
    return generate_password_hash(pwd, method="scrypt")


def verify_password(hash_value, pwd):
    try:
        return check_password_hash(hash_value, pwd)
    except Exception:
        return False


def current_user():
    if "user_id" not in session:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()


def inject_user():
    return {"user": current_user()}


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        u = current_user()
        if not u or u["is_blocked"]:
            session.clear()
            flash("Сессия недействительна. Войдите заново.", "error")
            return redirect(url_for("auth.login"))
        g.current_user = u
        return view(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    def deco(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            u = g.current_user
            if u["role"] not in roles:
                flash("Недостаточно прав для выполнения операции.", "error")
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return deco


def can_manage_employee(emp, user):
    if user is None:
        return False
    if user["role"] == "admin":
        return True
    if user["role"] == "manager":
        return emp["manager_id"] == user["id"]
    return False


def log_action(action, details=""):
    """A09: централизованный аудит."""
    u = current_user()
    db = get_db()
    db.execute(
        "INSERT INTO audit_log(user_id, action, details, ip, ua) VALUES (?,?,?,?,?)",
        (
            u["id"] if u else None,
            action,
            details[:500] if details else "",
            request.remote_addr if request else None,
            (request.headers.get("User-Agent") or "")[:300] if request else None,
        ),
    )


def rate_limit_login(username, ip):
    """A07: подсчёт неудачных попыток по (username, ip) за окно времени."""
    db = get_db()
    now = int(time.time())
    window = current_app.config["LOGIN_WINDOW_SECONDS"]
    db.execute(
        "DELETE FROM login_attempts WHERE ts < ?",
        (now - current_app.config["LOGIN_LOCKOUT_SECONDS"],),
    )
    row = db.execute(
        "SELECT COUNT(*) AS cnt FROM login_attempts "
        "WHERE username=? AND ip=? AND ts >= ?",
        (username, ip, now - window),
    ).fetchone()
    return row["cnt"]


def register_failed_login(username, ip):
    db = get_db()
    db.execute(
        "INSERT INTO login_attempts(username, ip, ts) VALUES (?,?,?)",
        (username, ip, int(time.time())),
    )


def clear_login_attempts(username, ip):
    db = get_db()
    db.execute("DELETE FROM login_attempts WHERE username=? AND ip=?", (username, ip))


def constant_time_compare(a, b):
    return hmac.compare_digest(str(a), str(b))