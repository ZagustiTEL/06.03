# blueprints/admin.py
# -*- coding: utf-8 -*-
"""Пользователи, бэкапы, аудит."""
import os
import sqlite3
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, current_app
)

from db import get_db, tx
from security import roles_required, log_action, hash_password
from validators import (
    parse_username, parse_password, parse_str, safe_backup_name, ValidationError
)
import backups as backups_mod

bp = Blueprint("admin", __name__)


@bp.route("/users")
@roles_required("admin")
def users():
    db = get_db()
    items = db.execute("SELECT * FROM users ORDER BY id").fetchall()
    return render_template("users.html", items=items)


@bp.route("/users/add", methods=["POST"])
@roles_required("admin")
def user_add():
    try:
        username = parse_username(request.form.get("username"))
        full_name = parse_str(request.form.get("full_name"), name="ФИО", max_len=200, required=True)
        password = parse_password(
            request.form.get("password"),
            min_len=current_app.config["PASSWORD_MIN_LENGTH"],
        )
        role = request.form.get("role")
        if role not in ("admin", "storekeeper", "operator", "manager"):
            raise ValidationError("Некорректная роль.")
    except ValidationError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.users"))

    db = get_db()
    try:
        with tx(db):
            db.execute(
                "INSERT INTO users(username, password_hash, full_name, role, must_change_password) "
                "VALUES (?,?,?,?,1)",
                (username, hash_password(password), full_name, role),
            )
        log_action("user_add", f"username={username}, role={role}")
        flash("Пользователь добавлен.", "success")
    except sqlite3.IntegrityError:
        flash("Логин уже занят.", "error")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:uid>/unblock", methods=["POST"])
@roles_required("admin")
def user_unblock(uid):
    db = get_db()
    with tx(db):
        db.execute("UPDATE users SET is_blocked=0, failed_attempts=0 WHERE id=?", (uid,))
        db.execute(
            "DELETE FROM login_attempts "
            "WHERE username=(SELECT username FROM users WHERE id=?)",
            (uid,),
        )
    log_action("user_unblock", f"id={uid}")
    flash("Пользователь разблокирован.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:uid>/reset", methods=["POST"])
@roles_required("admin")
def user_reset(uid):
    """A04: генерируем случайный пароль, показываем один раз."""
    import secrets
    new_password = secrets.token_urlsafe(12)
    db = get_db()
    with tx(db):
        db.execute(
            "UPDATE users SET password_hash=?, is_blocked=0, failed_attempts=0, "
            "must_change_password=1 WHERE id=?",
            (hash_password(new_password), uid),
        )
    log_action("user_reset", f"id={uid}")
    flash(f"Временный пароль: {new_password}. Пользователь обязан сменить его при входе.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/backups")
@roles_required("admin")
def backups_view():
    return render_template("backups.html", items=backups_mod.list_backups())


@bp.route("/backups/create", methods=["POST"])
@roles_required("admin")
def backup_create():
    try:
        p = backups_mod.make_backup()
    except Exception:
        current_app.logger.exception("Backup failed")
        flash("Не удалось создать бэкап.", "error")
        return redirect(url_for("admin.backups_view"))
    log_action("backup_create", os.path.basename(p) if p else "")
    flash(f"Бэкап создан: {os.path.basename(p)}" if p else "Не удалось создать бэкап.", "success")
    return redirect(url_for("admin.backups_view"))


@bp.route("/backups/restore", methods=["POST"])
@roles_required("admin")
def backup_restore():
    name = request.form.get("name", "")
    try:
        safe_name = safe_backup_name(name)
    except ValidationError:
        log_action("backup_restore_rejected", f"name={name!r}")
        flash("Недопустимое имя файла.", "error")
        return redirect(url_for("admin.backups_view"))

    ok, msg = backups_mod.restore_backup(safe_name)
    if ok:
        from flask import session
        session.clear()
        log_action("backup_restore", f"name={safe_name}")
        flash(msg + " Требуется повторный вход.", "success")
        return redirect(url_for("auth.login"))
    log_action("backup_restore_failed", f"name={safe_name}, msg={msg}")
    flash(msg, "error")
    return redirect(url_for("admin.backups_view"))


@bp.route("/audit")
@roles_required("admin")
def audit():
    """A09: просмотр журнала аудита."""
    db = get_db()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    per_page = 100
    offset = (page - 1) * per_page
    items = db.execute(
        "SELECT a.*, u.username FROM audit_log a "
        "LEFT JOIN users u ON u.id=a.user_id "
        "ORDER BY a.id DESC LIMIT ? OFFSET ?",
        (per_page, offset),
    ).fetchall()
    total = db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    return render_template("audit.html", items=items, page=page,
                           per_page=per_page, total=total)
