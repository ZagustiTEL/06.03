# blueprints/products.py
# -*- coding: utf-8 -*-
"""Товары."""
import sqlite3
from flask import Blueprint, render_template, request, redirect, url_for, flash

from db import get_db
from security import roles_required, log_action
from validators import parse_int, parse_float, parse_str, ValidationError

bp = Blueprint("products", __name__)


@bp.route("/products")
@roles_required("admin", "manager", "storekeeper", "operator")
def list_products():
    db = get_db()
    items = db.execute("SELECT * FROM products ORDER BY name").fetchall()
    return render_template("products.html", products=items)


@bp.route("/products/add", methods=["POST"])
@roles_required("admin", "storekeeper", "operator")
def product_add():
    try:
        sku = parse_str(request.form.get("sku"), name="артикул", max_len=64, required=True)
        name = parse_str(request.form.get("name"), name="наименование", max_len=200, required=True)
        unit = parse_str(request.form.get("unit") or "шт", name="ед. изм.", max_len=16)
        price = parse_float(request.form.get("price") or 0, name="цена", min_value=0, max_value=1e9)
        qty = parse_int(request.form.get("quantity") or 0, name="остаток", min_value=0, max_value=10**9)
        minq = parse_int(request.form.get("min_quantity") or 0, name="мин. остаток", min_value=0, max_value=10**9)
    except ValidationError as e:
        flash(str(e), "error")
        return redirect(url_for("products.list_products"))

    db = get_db()
    try:
        db.execute(
            "INSERT INTO products(sku,name,unit,price,quantity,min_quantity) VALUES (?,?,?,?,?,?)",
            (sku, name, unit, price, qty, minq),
        )
        log_action("product_add", f"sku={sku}")
        flash("Товар добавлен.", "success")
    except sqlite3.IntegrityError:
        flash("Артикул уже существует.", "error")
    return redirect(url_for("products.list_products"))


@bp.route("/products/delete/<int:pid>", methods=["POST"])
@roles_required("admin")
def product_delete(pid):
    db = get_db()
    db.execute("DELETE FROM products WHERE id=?", (pid,))
    log_action("product_delete", f"id={pid}")
    flash("Товар удалён.", "success")
    return redirect(url_for("products.list_products"))