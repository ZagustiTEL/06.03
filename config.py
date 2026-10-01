# config.py
# -*- coding: utf-8 -*-
"""Конфигурация приложения."""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # --- A02/A04: секрет обязателен, не генерируется случайно ---
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError(
            "Переменная окружения SECRET_KEY не задана. "
            "Сгенерируйте: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    DB_PATH = os.environ.get("SKLAD_DB_PATH") or os.path.join(BASE_DIR, "sklad.db")
    BACKUP_DIR = os.environ.get("SKLAD_BACKUP_DIR") or os.path.join(BASE_DIR, "backups")
    BACKUP_HMAC_KEY = os.environ.get("BACKUP_HMAC_KEY") or SECRET_KEY

    MAX_LOGIN_ATTEMPTS = 5
    LOGIN_WINDOW_SECONDS = 300        # окно для подсчёта попыток
    LOGIN_LOCKOUT_SECONDS = 900       # блокировка на 15 минут
    MAX_BACKUPS = 30                  # A06: ротация бэкапов
    PASSWORD_MIN_LENGTH = 10
    PASSWORD_RESET_DEFAULT = None     # A04: не сбрасываем на фиксированный пароль
    DEFAULT_ADMIN_PASSWORD = os.environ.get("SKLAD_ADMIN_PASSWORD") or "ChangeMe_12345!"

    # --- A07: cookie ---
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Secure включается автоматически, если приложение за HTTPS
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_HTTPS") == "1"
    PERMANENT_SESSION_LIFETIME = 3600 * 8   # 8 часов
    SESSION_REFRESH_EACH_REQUEST = True

    # --- A02: CSRF ---
    WTF_CSRF_TIME_LIMIT = 3600 * 4       # 4 часа, не бессрочно
    WTF_CSRF_SSL_STRICT = True

    # --- Прочее ---
    DEBUG = False
    TESTING = False
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024