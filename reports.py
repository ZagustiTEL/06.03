# reports.py
# -*- coding: utf-8 -*-
"""Построение отчётов."""
from db import get_db


ALLOWED_KINDS = {"stock", "profit", "movements"}


def build_report(kind, date_from=None, date_to=None):
    if kind not in ALLOWED_KINDS:
        kind = "stock"
    db = get_db()

    if kind == "profit":
        title = "Финансовый отчёт по месяцам"
        sql = """
            SELECT strftime('%Y-%m', created_at) AS m,
                   COALESCE(SUM(CASE WHEN kind='income'  THEN amount END), 0) AS inc,
                   COALESCE(SUM(CASE WHEN kind='expense' THEN amount END), 0) AS exp
            FROM finance
            WHERE 1=1
        """
        params = []
        if date_from:
            sql += " AND DATE(created_at) >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND DATE(created_at) <= ?"
            params.append(date_to)
        sql += " GROUP BY m ORDER BY m DESC"
        rows = db.execute(sql, params).fetchall()
        headers = ["Месяц", "Доходы, руб.", "Расходы, руб.", "Прибыль, руб."]
        data = [
            [r["m"], f"{r['inc']:.2f}", f"{r['exp']:.2f}", f"{r['inc'] - r['exp']:.2f}"]
            for r in rows
        ]
        return title, headers, data

    if kind == "movements":
        title = "Движения товаров"
        records = []
        # Явный whitelist таблиц — никогда не подставляем ввод пользователя
        for tbl, label in (("receipts", "Приём"),
                           ("shipments", "Отправка"),
                           ("writeoffs", "Списание")):
            sql = (
                f"SELECT t.created_at AS created_at, p.sku AS sku, "
                f"p.name AS name, t.quantity AS quantity "
                f"FROM {tbl} t JOIN products p ON p.id = t.product_id WHERE 1=1"
            )
            params = []
            if date_from:
                sql += " AND DATE(t.created_at) >= ?"
                params.append(date_from)
            if date_to:
                sql += " AND DATE(t.created_at) <= ?"
                params.append(date_to)
            for r in db.execute(sql, params).fetchall():
                records.append([r["created_at"], label, r["sku"], r["name"], r["quantity"]])
        records.sort(key=lambda x: x[0], reverse=True)
        headers = ["Дата", "Тип", "Артикул", "Наименование", "Кол-во"]
        return title, headers, records

    title = "Остатки на складе"
    rows = db.execute(
        "SELECT sku, name, unit, quantity, price FROM products ORDER BY name"
    ).fetchall()
    headers = ["Артикул", "Наименование", "Ед.", "Остаток", "Цена, руб.", "Стоимость, руб."]
    data = [
        [r["sku"], r["name"], r["unit"], r["quantity"],
         f"{r['price']:.2f}", f"{r['quantity'] * r['price']:.2f}"]
        for r in rows
    ]
    return title, headers, data