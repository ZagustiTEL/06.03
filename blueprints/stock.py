# blueprints/stock.py
# -*- coding: utf-8 -*-
"""Приём, отгрузка, списание (A06: транзакции, A10: валидация)."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session

from db import get_db, tx
from security import roles_required, log_action
from validators import parse_int, parse_str, ValidationError

bp = Blueprint("stock", __name__)

STOCK_ROLES = ("admin", "storekeeper", "operator")


@bp.route("/receipts", methods=["GET", "POST"])
@roles_required(*STOCK_ROLES)
def receipts():
    db = get_db()
    if request.method == "POST":
        try:
            pid = parse_int(request.form.get("product_id"), name="товар", min_value=1)
            qty = parse_int(request.form.get("quantity"), name="количество", min_value=1, max_value=10**7)
            supplier = parse_str(request.form.get("supplier"), name="поставщик", max_len=200)
            comment = parse_str(request.form.get("comment"), name="комментарий", max_len=500)
        except ValidationError as e:
            flash(str(e), "error")
            return redirect(url_for("stock.receipts"))

        with tx(db):
            p = db.execute("SELECT id FROM products WHERE id=?", (pid,)).fetchone()
            if not p:
                flash("Товар не найден.", "error")
                return redirect(url_for("stock.receipts"))
            db.execute(
                "INSERT INTO receipts(product_id, quantity, supplier, comment, user_id) "
                "VALUES (?,?,?,?,?)",
                (pid, qty, supplier, comment, _uid()),
            )
            db.execute("UPDATE products SET quantity = quantity + ? WHERE id=?", (qty, pid))

        log_action("receipt", f"product_id={pid}, qty={qty}")
        flash("Товар принят на склад.", "success")
        return redirect(url_for("stock.receipts"))

    items = db.execute("""
        SELECT r.*, p.sku, p.name, u.full_name AS user_name
        FROM receipts r
        JOIN products p ON p.id=r.product_id
        LEFT JOIN users u ON u.id=r.user_id
        ORDER BY r.created_at DESC LIMIT 100
    """).fetchall()
    prods = db.execute("SELECT * FROM products ORDER BY name").fetchall()
    return render_template("receipts.html", items=items, products=prods)


@bp.route("/shipments", methods=["GET", "POST"])
@roles_required(*STOCK_ROLES)
def shipments():
    db = get_db()
    if request.method == "POST":
        try:
            pid = parse_int(request.form.get("product_id"), name="товар", min_value=1)
            qty = parse_int(request.form.get("quantity"), name="количество", min_value=1, max_value=10**7)
            destination = parse_str(request.form.get("destination"), name="получатель", max_len=200)
            comment = parse_str(request.form.get("comment"), name="комментарий", max_len=500)
        except ValidationError as e:
            flash(str(e), "error")
            return redirect(url_for("stock.shipments"))

        with tx(db):
            p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            if not p:
                flash("Товар не найден.", "error")
                return redirect(url_for("stock.shipments"))
            if p["quantity"] < qty:
                flash("Недостаточно товара на складе.", "error")
                return redirect(url_for("stock.shipments"))
            db.execute(
                "INSERT INTO shipments(product_id, quantity, destination, comment, user_id) "
                "VALUES (?,?,?,?,?)",
                (pid, qty, destination, comment, _uid()),
            )
            db.execute("UPDATE products SET quantity = quantity - ? WHERE id=?", (qty, pid))
            db.execute(
                "INSERT INTO finance(kind, amount, description, user_id) VALUES ('income',?,?,?)",
                (qty * p["price"], f"Отгрузка {p['sku']} x{qty}", _uid()),
            )

        log_action("shipment", f"product_id={pid}, qty={qty}")
        flash("Товар отправлен со склада.", "success")
        return redirect(url_for("stock.shipments"))

    items = db.execute("""
        SELECT s.*, p.sku, p.name, u.full_name AS user_name
        FROM shipments s
        JOIN products p ON p.id=s.product_id
        LEFT JOIN users u ON u.id=s.user_id
        ORDER BY s.created_at DESC LIMIT 100
    """).fetchall()
    prods = db.execute("SELECT * FROM products ORDER BY name").fetchall()
    return render_template("shipments.html", items=items, products=prods)


@bp.route("/writeoffs", methods=["GET", "POST"])
@roles_required(*STOCK_ROLES)
def writeoffs():
    db = get_db()
    if request.method == "POST":
        try:
            pid = parse_int(request.form.get("product_id"), name="товар", min_value=1)
            qty = parse_int(request.form.get("quantity"), name="количество", min_value=1, max_value=10**7)
            reason = parse_str(request.form.get("reason"), name="причина", max_len=300)
        except ValidationError as e:
            flash(str(e), "error")
            return redirect(url_for("stock.writeoffs"))

        with tx(db):
            p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            if not p:
                flash("Товар не найден.", "error")
                return redirect(url_for("stock.writeoffs"))
            if p["quantity"] < qty:
                flash("Недостаточно товара для списания.", "error")
                return redirect(url_for("stock.writeoffs"))
            db.execute(
                "INSERT INTO writeoffs(product_id, quantity, reason, user_id) VALUES (?,?,?,?)",
                (pid, qty, reason, _uid()),
            )
            db.execute("UPDATE products SET quantity = quantity - ? WHERE id=?", (qty, pid))
            db.execute(
                "INSERT INTO finance(kind, amount, description, user_id) VALUES ('expense',?,?,?)",
                (qty * p["price"], f"Списание {p['sku']} x{qty}", _uid()),
            )

        log_action("writeoff", f"product_id={pid}, qty={qty}")
        flash("Товар списан.", "success")
        return redirect(url_for("stock.writeoffs"))

    items = db.execute("""
        SELECT w.*, p.sku, p.name, u.full_name AS user_name
        FROM writeoffs w
        JOIN products p ON p.id=w.product_id
        LEFT JOIN users u ON u.id=w.user_id
        ORDER BY w.created_at DESC LIMIT 100
    """).fetchall()
    prods = db.execute("SELECT * FROM products ORDER BY name").fetchall()
    return render_template("writeoffs.html", items=items, products=prods)


def _uid():
    return session.get("user_id")
