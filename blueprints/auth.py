# blueprints/auth.py
# -*- coding: utf-8 -*-
"""Аутентификация."""
from flask import (
    Blueprint, request, session, redirect, url_for, render_template, flash
)

from db import get_db
from security import (
    verify_password, hash_password, log_action,
    rate_limit_login, register_failed_login, clear_login_attempts,
    _DUMMY_HASH,
)
from validators import parse_password, ValidationError
from flask import current_app

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        ip = request.remote_addr or "unknown"

        max_attempts = current_app.config["MAX_LOGIN_ATTEMPTS"]
        if rate_limit_login(username, ip) >= max_attempts:
            log_action("login_rate_limited", f"username={username}, ip={ip}")
            flash("Слишком много попыток входа. Учётная запись заблокирована.", "error")
            return render_template("login.html"), 429

        db = get_db()
        u = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

        # A07: если пользователя нет — всё равно делаем dummy-проверку,
        # чтобы timing не выдавал существование логина
        stored_hash = u["password_hash"] if u else _DUMMY_HASH
        ok = verify_password(stored_hash, password)

        if not u or not ok:
            register_failed_login(username, ip)
            log_action("login_failed", f"username={username}, ip={ip}")
            flash("Неверный логин или пароль.", "error")
            return render_template("login.html"), 401

        if u["is_blocked"]:
            log_action("login_blocked", f"username={username}, ip={ip}")
            flash("Учётная запись заблокирована. Обратитесь к администратору.", "error")
            return render_template("login.html"), 403

        # успех
        clear_login_attempts(username, ip)
        db.execute("UPDATE users SET failed_attempts=0 WHERE id=?", (u["id"],))

        # A07: ротация session id
        session.clear()
        session["user_id"] = u["id"]
        session.permanent = True

        log_action("login", f"username={username}, ip={ip}")

        if u["must_change_password"]:
            flash("Смените пароль после первого входа.", "error")
            return redirect(url_for("auth.change_password"))
        return redirect(url_for("index"))

    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    log_action("logout", "")
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    from security import current_user
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    u = current_user()
    if not u:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        old = request.form.get("old_password") or ""
        new = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""

        if not verify_password(u["password_hash"], old):
            flash("Неверный текущий пароль.", "error")
            return render_template("change_password.html")

        if new != confirm:
            flash("Новый пароль и подтверждение не совпадают.", "error")
            return render_template("change_password.html")

        try:
            parse_password(new, min_len=current_app.config["PASSWORD_MIN_LENGTH"])
        except ValidationError as e:
            flash(str(e), "error")
            return render_template("change_password.html")

        db = get_db()
        db.execute(
            "UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?",
            (hash_password(new), u["id"]),
        )
        log_action("password_change", f"user_id={u['id']}")
        flash("Пароль изменён.", "success")
        return redirect(url_for("index"))

    return render_template("change_password.html")
