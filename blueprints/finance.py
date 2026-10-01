# blueprints/finance.py
# -*- coding: utf-8 -*-
"""Финансы."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, g

from db import get_db, tx
from security import roles_required, log_action
from validators import parse_float, parse_str, ValidationError

bp = Blueprint("finance", __name__)


@bp.route("/finance", methods=["GET", "POST"])
@roles_required("admin", "manager")
def finance():
    db = get_db()
    if request.method == "POST":
        kind = request.form.get("kind")
        if kind not in ("income", "expense"):
            flash("Некорректный тип операции.", "error")
            return redirect(url_for("finance.finance"))
        try:
            amount = parse_float(request.form.get("amount"), name="сумма",
                                 min_value=0.01, max_value=1e12)
            description = parse_str(request.form.get("description"), name="описание", max_len=500)
        except ValidationError as e:
            flash(str(e), "error")
            return redirect(url_for("finance.finance"))

        with tx(db):
            db.execute(
                "INSERT INTO finance(kind, amount, description, user_id) VALUES (?,?,?,?)",
                (kind, amount, description, g.current_user["id"]),
            )
        log_action("finance_add", f"kind={kind}, amount={amount}")
        flash("Операция добавлена.", "success")
        return redirect(url_for("finance.finance"))

    income = db.execute("SELECT COALESCE(SUM(amount),0) FROM finance WHERE kind='income'").fetchone()[0]
    expense = db.execute("SELECT COALESCE(SUM(amount),0) FROM finance WHERE kind='expense'").fetchone()[0]
    items = db.execute("SELECT * FROM finance ORDER BY created_at DESC LIMIT 200").fetchall()
    return render_template("finance.html", items=items, income=income, expense=expense)