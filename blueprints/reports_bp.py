# blueprints/reports_bp.py
# -*- coding: utf-8 -*-
"""Отчёты."""
from flask import Blueprint, render_template, request, flash

from db import get_db
from security import roles_required
from reports import build_report, ALLOWED_KINDS
from export import send_report
from validators import parse_optional_date, ValidationError

bp = Blueprint("reports", __name__)

REPORT_ROLES = ("admin", "manager", "storekeeper", "operator")


@bp.route("/reports")
@roles_required(*REPORT_ROLES)
def reports():
    db = get_db()
    totals = {
        "products": db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "total_qty": db.execute("SELECT COALESCE(SUM(quantity),0) FROM products").fetchone()[0],
        "stock_value": db.execute(
            "SELECT COALESCE(SUM(quantity * price),0) FROM products"
        ).fetchone()[0],
    }
    by_type = []
    for tbl, label in (("receipts", "Приём"),
                       ("shipments", "Отправка"),
                       ("writeoffs", "Списание")):
        row = db.execute(
            f"SELECT COUNT(*) AS cnt, COALESCE(SUM(quantity),0) AS total_qty FROM {tbl}"
        ).fetchone()
        by_type.append({"type": label, "cnt": row["cnt"], "total_qty": row["total_qty"]})
    top = db.execute("""
        SELECT sku, name, unit, quantity, quantity * price AS total
        FROM products
        ORDER BY quantity DESC
        LIMIT 10
    """).fetchall()
    return render_template("reports.html", totals=totals, by_type=by_type, top=top)


@bp.route("/reports/generate")
@roles_required(*REPORT_ROLES)
def report_generate():
    kind = request.args.get("kind", "stock")
    if kind not in ALLOWED_KINDS:
        kind = "stock"
    try:
        date_from = parse_optional_date(request.args.get("date_from"))
        date_to = parse_optional_date(request.args.get("date_to"))
    except ValidationError as e:
        flash(str(e), "error")
        date_from = date_to = None
    title, headers, data = build_report(kind, date_from, date_to)
    return render_template(
        "report_view.html",
        title=title, headers=headers, data=data,
        kind=kind, date_from=date_from, date_to=date_to,
    )


@bp.route("/reports/export")
@roles_required(*REPORT_ROLES)
def report_export():
    kind = request.args.get("kind", "stock")
    fmt = request.args.get("fmt", "pdf")
    try:
        date_from = parse_optional_date(request.args.get("date_from"))
        date_to = parse_optional_date(request.args.get("date_to"))
    except ValidationError:
        date_from = date_to = None
    return send_report(kind, fmt, date_from, date_to)
