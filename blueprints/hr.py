# blueprints/hr.py
# -*- coding: utf-8 -*-
"""Персонал, смены, зарплата."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, g

from db import get_db, tx
from security import roles_required, can_manage_employee, log_action
from validators import (
    parse_int, parse_float, parse_str, parse_date, parse_period, ValidationError
)

bp = Blueprint("hr", __name__)


@bp.route("/employees")
@roles_required("admin", "manager")
def employees():
    db = get_db()
    u = g.current_user
    if u["role"] == "admin":
        items = db.execute("SELECT * FROM employees ORDER BY full_name").fetchall()
    else:
        items = db.execute(
            "SELECT * FROM employees WHERE manager_id=? ORDER BY full_name",
            (u["id"],),
        ).fetchall()
    return render_template("employees.html", items=items)


@bp.route("/employees/add", methods=["POST"])
@roles_required("admin", "manager")
def employee_add():
    try:
        full_name = parse_str(request.form.get("full_name"), name="ФИО", max_len=200, required=True)
        position = parse_str(request.form.get("position"), name="должность", max_len=100)
        salary = parse_float(request.form.get("salary") or 0, name="оклад", min_value=0, max_value=1e9)
    except ValidationError as e:
        flash(str(e), "error")
        return redirect(url_for("hr.employees"))

    db = get_db()
    u = g.current_user
    manager_id = u["id"] if u["role"] == "manager" else None
    with tx(db):
        db.execute(
            "INSERT INTO employees(full_name, position, salary, manager_id) VALUES (?,?,?,?)",
            (full_name, position, salary, manager_id),
        )
    log_action("employee_add", full_name)
    flash("Сотрудник добавлен.", "success")
    return redirect(url_for("hr.employees"))


@bp.route("/employees/<int:eid>/edit", methods=["GET", "POST"])
@roles_required("admin", "manager")
def employee_edit(eid):
    db = get_db()
    emp = db.execute("SELECT * FROM employees WHERE id=?", (eid,)).fetchone()
    if not emp:
        abort(404)
    if not can_manage_employee(emp, g.current_user):
        abort(403)
    if request.method == "POST":
        try:
            full_name = parse_str(request.form.get("full_name"), name="ФИО", max_len=200, required=True)
            position = parse_str(request.form.get("position"), name="должность", max_len=100)
            salary = parse_float(request.form.get("salary") or 0, name="оклад", min_value=0, max_value=1e9)
        except ValidationError as e:
            flash(str(e), "error")
            return redirect(url_for("hr.employee_edit", eid=eid))
        with tx(db):
            db.execute(
                "UPDATE employees SET full_name=?, position=?, salary=? WHERE id=?",
                (full_name, position, salary, eid),
            )
        log_action("employee_edit", f"id={eid}, {full_name}")
        flash("Данные сотрудника обновлены.", "success")
        return redirect(url_for("hr.employees"))
    return render_template("employee_edit.html", emp=emp)


@bp.route("/employees/<int:eid>/delete", methods=["POST"])
@roles_required("admin")
def employee_delete(eid):
    db = get_db()
    emp = db.execute("SELECT * FROM employees WHERE id=?", (eid,)).fetchone()
    if not emp:
        abort(404)
    with tx(db):
        db.execute("DELETE FROM shifts WHERE employee_id=?", (eid,))
        db.execute("DELETE FROM payroll WHERE employee_id=?", (eid,))
        db.execute("DELETE FROM employees WHERE id=?", (eid,))
    log_action("employee_delete", f"id={eid}, {emp['full_name']}")
    flash("Сотрудник удалён.", "success")
    return redirect(url_for("hr.employees"))


@bp.route("/employees/<int:eid>/shifts", methods=["GET", "POST"])
@roles_required("admin", "manager")
def employee_shifts(eid):
    db = get_db()
    emp = db.execute("SELECT * FROM employees WHERE id=?", (eid,)).fetchone()
    if not emp:
        abort(404)
    if not can_manage_employee(emp, g.current_user):
        abort(403)

    if request.method == "POST":
        try:
            work_date = parse_date(request.form.get("work_date"), name="дата смены")
            hours = parse_float(request.form.get("hours") or 8, name="часы", min_value=0.5, max_value=12)
            note = parse_str(request.form.get("note"), name="примечание", max_len=300)
        except ValidationError as e:
            flash(str(e), "error")
            return redirect(url_for("hr.employee_shifts", eid=eid))
        with tx(db):
            db.execute(
                "INSERT INTO shifts(employee_id, work_date, hours, note) VALUES (?,?,?,?)",
                (eid, work_date, hours, note),
            )
        log_action("shift_add", f"employee_id={eid}, date={work_date}")
        flash("Смена добавлена.", "success")
        return redirect(url_for("hr.employee_shifts", eid=eid))

    items = db.execute(
        "SELECT * FROM shifts WHERE employee_id=? ORDER BY work_date DESC", (eid,)
    ).fetchall()
    return render_template("shifts.html", emp=emp, items=items)


@bp.route("/payroll", methods=["GET", "POST"])
@roles_required("admin", "manager")
def payroll():
    db = get_db()
    u = g.current_user
    current_period = __import__("datetime").date.today().strftime("%Y-%m")

    if request.method == "POST":
        try:
            period = parse_period(request.form.get("period"))
        except ValidationError as e:
            flash(str(e), "error")
            return redirect(url_for("hr.payroll"))

        if u["role"] == "admin":
            emps = db.execute("SELECT * FROM employees").fetchall()
        else:
            emps = db.execute(
                "SELECT * FROM employees WHERE manager_id=?", (u["id"],)
            ).fetchall()

        with tx(db):
            for e in emps:
                # Проверяем, не рассчитана ли уже ЗП за этот период
                exists = db.execute(
                    "SELECT 1 FROM payroll WHERE employee_id=? AND period=?",
                    (e["id"], period),
                ).fetchone()
                if exists:
                    continue
                hours = db.execute(
                    "SELECT COALESCE(SUM(hours),0) FROM shifts "
                    "WHERE employee_id=? AND strftime('%Y-%m', work_date)=?",
                    (e["id"], period),
                ).fetchone()[0]
                amount = e["salary"] * (hours / 160.0) if hours else 0
                db.execute(
                    "INSERT INTO payroll(employee_id, period, hours, amount) VALUES (?,?,?,?)",
                    (e["id"], period, hours, amount),
                )
                if amount > 0:
                    db.execute(
                        "INSERT INTO finance(kind, amount, description, user_id) "
                        "VALUES ('expense',?,?,?)",
                        (amount, f"Зарплата {e['full_name']} за {period}", u["id"]),
                    )
        log_action("payroll", f"period={period}")
        flash(f"Зарплата за {period} рассчитана.", "success")
        return redirect(url_for("hr.payroll"))

    if u["role"] == "admin":
        items = db.execute("""
            SELECT p.*, e.full_name FROM payroll p
            JOIN employees e ON e.id=p.employee_id
            ORDER BY p.created_at DESC LIMIT 200
        """).fetchall()
    else:
        items = db.execute("""
            SELECT p.*, e.full_name FROM payroll p
            JOIN employees e ON e.id=p.employee_id
            WHERE e.manager_id=?
            ORDER BY p.created_at DESC LIMIT 200
        """, (u["id"],)).fetchall()
    return render_template("payroll.html", items=items, current_period=current_period)