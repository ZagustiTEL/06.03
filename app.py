# app.py
# -*- coding: utf-8 -*-
"""Точка входа АИС «Склад»."""
import os
import datetime

from flask import Flask, render_template, redirect, url_for, g, session

from config import Config
from db import init_app as init_db_app, get_db
from security import (
    init_app as init_security_app, login_required, current_user,
    inject_user, log_action,
)
import backups as backups_mod


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(app.config["BACKUP_DIR"], exist_ok=True)

    # БД
    init_db_app(app)
    # CSRF + auth
    init_security_app(app)

    # Контекст-процессор user
    app.context_processor(inject_user)

    # Blueprint'ы
    from blueprints.auth import bp as auth_bp
    from blueprints.products import bp as products_bp
    from blueprints.stock import bp as stock_bp
    from blueprints.hr import bp as hr_bp
    from blueprints.finance import bp as finance_bp
    from blueprints.admin import bp as admin_bp
    from blueprints.reports_bp import bp as reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(stock_bp)
    app.register_blueprint(hr_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(reports_bp)

    # --- главная ---
    @app.route("/")
    @login_required
    def index():
        db = get_db()
        today = datetime.date.today().isoformat()
        month = datetime.date.today().strftime("%Y-%m")
        stats = {
            "products": db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "total_qty": db.execute("SELECT COALESCE(SUM(quantity),0) FROM products").fetchone()[0],
            "receipts_today": db.execute(
                "SELECT COUNT(*) FROM receipts WHERE DATE(created_at)=?", (today,)
            ).fetchone()[0],
            "shipments_today": db.execute(
                "SELECT COUNT(*) FROM shipments WHERE DATE(created_at)=?", (today,)
            ).fetchone()[0],
            "employees": db.execute("SELECT COUNT(*) FROM employees").fetchone()[0],
            "low_stock": db.execute(
                "SELECT * FROM products WHERE quantity <= min_quantity ORDER BY quantity"
            ).fetchall(),
        }
        income = db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM finance "
            "WHERE kind='income' AND strftime('%Y-%m',created_at)=?", (month,)
        ).fetchone()[0]
        expense = db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM finance "
            "WHERE kind='expense' AND strftime('%Y-%m',created_at)=?", (month,)
        ).fetchone()[0]
        stats["profit"] = income - expense

        try:
            backups_mod.daily_backup_if_needed()
        except Exception:
            app.logger.exception("Daily backup failed")

        return render_template("index.html", stats=stats)

    # --- обработчики ошибок ---
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403,
                               message="Доступ запрещён."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404,
                               message="Страница не найдена."), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Internal server error")
        return render_template("error.html", code=500,
                               message="Внутренняя ошибка сервера."), 500

    return app


app = create_app()


if __name__ == "__main__":
    import db_init
    db_init.init_db(force=False)
    debug = os.environ.get("FLASK_DEBUG") == "1"
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    app.logger.info("АИС «Склад» запущена на http://%s:%d (debug=%s)", host, port, debug)
    app.run(host=host, port=port, debug=debug)