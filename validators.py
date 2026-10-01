# validators.py
# -*- coding: utf-8 -*-
"""Валидация входных данных (A10: обработка нештатных ситуаций)."""
import math
import re
from werkzeug.utils import secure_filename


class ValidationError(ValueError):
    pass


def parse_int(value, *, name="значение", min_value=None, max_value=None):
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"Некорректное {name}: ожидается целое число.")
    if min_value is not None and n < min_value:
        raise ValidationError(f"{name.capitalize()} должно быть >= {min_value}.")
    if max_value is not None and n > max_value:
        raise ValidationError(f"{name.capitalize()} должно быть <= {max_value}.")
    return n


def parse_float(value, *, name="значение", min_value=None, max_value=None):
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"Некорректное {name}: ожидается число.")
    if math.isnan(n) or math.isinf(n):
        raise ValidationError(f"Некорректное {name}: NaN/Inf не допускаются.")
    if min_value is not None and n < min_value:
        raise ValidationError(f"{name.capitalize()} должно быть >= {min_value}.")
    if max_value is not None and n > max_value:
        raise ValidationError(f"{name.capitalize()} должно быть <= {max_value}.")
    return n


def parse_str(value, *, name="значение", max_len=500, required=False, strip=True):
    if value is None:
        value = ""
    if not isinstance(value, str):
        value = str(value)
    if strip:
        value = value.strip()
    if required and not value:
        raise ValidationError(f"Поле «{name}» обязательно.")
    if len(value) > max_len:
        raise ValidationError(f"Поле «{name}» превышает {max_len} символов.")
    return value


def parse_password(value, *, min_len=10):
    if not isinstance(value, str):
        raise ValidationError("Пароль должен быть строкой.")
    if len(value) < min_len:
        raise ValidationError(f"Пароль должен быть не короче {min_len} символов.")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValidationError("Пароль должен содержать буквы и цифры.")
    return value


def parse_username(value, *, name="логин"):
    value = parse_str(value, name=name, max_len=64, required=True)
    if not re.match(r"^[A-Za-z0-9_.-]{3,64}$", value):
        raise ValidationError(
            "Логин: 3–64 символа, только латиница, цифры, . _ -"
        )
    return value


def parse_period(value):
    value = parse_str(value, name="период", max_len=7, required=True)
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", value):
        raise ValidationError("Период должен быть в формате YYYY-MM.")
    return value


def parse_date(value, *, name="дата"):
    value = parse_str(value, name=name, max_len=10, required=True)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        raise ValidationError(f"{name.capitalize()} должна быть в формате YYYY-MM-DD.")
    return value


def parse_optional_date(value):
    if value is None or value == "":
        return None
    return parse_date(value)


def safe_backup_name(name):
    """A01: защита от path traversal в имени бэкапа."""
    if not isinstance(name, str):
        raise ValidationError("Некорректное имя файла бэкапа.")
    # Никаких разделителей пути
    if "/" in name or "\\" in name or ".." in name:
        raise ValidationError("Недопустимое имя файла бэкапа.")
    base = secure_filename(name)
    if base != name or not base:
        raise ValidationError("Недопустимое имя файла бэкапа.")
    return base


def sanitize_cell(value):
    """A05: защита от Excel formula injection."""
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s