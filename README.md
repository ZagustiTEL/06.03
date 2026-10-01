# АИС «Склад»

Веб-приложение на Flask для складского учёта: товары, приём, отгрузка, списание, персонал, смены, расчёт зарплаты, финансы, отчёты, аудит и резервное копирование.

---

## Содержание

- [Возможности](#возможности)
- [Роли](#роли)
- [Стек](#стек)
- [Быстрый старт](#быстрый-старт)
- [Переменные окружения](#переменные-окружения)
- [Структура проекта](#структура-проекта)
- [Резервное копирование](#резервное-копирование)
- [Отчёты и экспорт](#отчёты-и-экспорт)
- [Безопасность](#безопасность)

---

## Возможности

- **Аутентификация и роли** — вход по логину/паролю, обязательная смена пароля при первом входе, блокировка при переборе, аудит действий.
- **Товары** — добавление, удаление, остатки, минимальный остаток, цена, артикул.
- **Складские операции** — приём, отгрузка, списание, автоматическое обновление остатков и финансов.
- **Персонал** — сотрудники, смены, расчёт зарплаты за период, привязка к менеджеру.
- **Финансы** — доходы, расходы, прибыль.
- **Отчёты** — остатки на складе, финансовый отчёт по месяцам, движения товаров; экспорт в PDF и XLSX.
- **Администрирование** — управление пользователями, разблокировка, сброс пароля, журнал аудита, резервное копирование и восстановление.
- **Безопасность** — CSRF, HMAC-подпись бэкапов, защита от path traversal и formula injection, rate limiting, scrypt, транзакции `BEGIN IMMEDIATE`, безопасные cookie.

---

## Роли

| Роль | Права |
|---|---|
| `admin` | Полный доступ: пользователи, бэкапы, аудит, товары, склад, HR, финансы, отчёты |
| `storekeeper` | Товары, приём, отгрузка, списание, отчёты |
| `operator` | Товары, приём, отгрузка, списание, отчёты |
| `manager` | Персонал, смены, зарплата, финансы, отчёты |

---

## Стек

- Python 3.8+
- Flask 3.0.3
- Flask-WTF 1.2.1
- Werkzeug 3.0.4
- SQLite
- openpyxl 3.1.5
- reportlab 4.2.2
- pytest — для тестов

---

## Быстрый старт

### 1. Клонирование репозитория

```bash
git clone <URL_РЕПОЗИТОРИЯ>
cd <ПАПКА_ПРОЕКТА>
```

### 2. Виртуальное окружение

**Linux/macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows:**

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
pip install pytest   # для запуска тестов
```

### 4. Переменные окружения

Обязательно задайте `SECRET_KEY` — без него приложение не запустится.

**Linux/macOS:**

```bash
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export BACKUP_HMAC_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export SKLAD_DB_PATH="$PWD/sklad.db"
export SKLAD_BACKUP_DIR="$PWD/backups"
export SKLAD_ADMIN_PASSWORD="StrongAdminPass123"
```

**Windows (PowerShell):**

```powershell
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
$env:BACKUP_HMAC_KEY = python -c "import secrets; print(secrets.token_hex(32))"
$env:SKLAD_DB_PATH = "$PWD\sklad.db"
$env:SKLAD_BACKUP_DIR = "$PWD\backups"
$env:SKLAD_ADMIN_PASSWORD = "StrongAdminPass123"
```

> Если `SKLAD_ADMIN_PASSWORD` не задан — при инициализации будет создан случайный пароль администратора и выведен в консоль один раз.

### 5. Инициализация базы данных

```bash
python db_init.py
```

Будут созданы таблицы, индексы и начальный администратор.

### 6. Запуск приложения

```bash
python app.py
```

По умолчанию приложение доступно по адресу: <http://127.0.0.1:5000>

### 7. Тесты

```bash
pytest -q
```

---

## Переменные окружения

| Переменная | Обязательна | Назначение |
|---|:---:|---|
| `SECRET_KEY` | ✅ | Секрет Flask для подписи сессий и CSRF |
| `BACKUP_HMAC_KEY` | ❌ | Ключ HMAC для подписи бэкапов. Если не задан — используется `SECRET_KEY` |
| `SKLAD_DB_PATH` | ❌ | Путь к файлу SQLite. По умолчанию `./sklad.db` |
| `SKLAD_BACKUP_DIR` | ❌ | Каталог резервных копий. По умолчанию `./backups` |
| `SKLAD_ADMIN_PASSWORD` | ❌ | Пароль администратора при первичной инициализации |
| `FLASK_HTTPS` | ❌ | `1` — включает `Secure` для session cookie |
| `FLASK_DEBUG` | ❌ | `1` — режим отладки Flask |
| `FLASK_HOST` | ❌ | Хост запуска. По умолчанию `127.0.0.1` |
| `FLASK_PORT` | ❌ | Порт запуска. По умолчанию `5000` |

Дополнительные параметры — в `config.py`:

- `MAX_LOGIN_ATTEMPTS`
- `LOGIN_WINDOW_SECONDS`
- `LOGIN_LOCKOUT_SECONDS`
- `MAX_BACKUPS`
- `PASSWORD_MIN_LENGTH`
- `PERMANENT_SESSION_LIFETIME`
- `MAX_CONTENT_LENGTH`

---

## Структура проекта

```
.
├── app.py                  # Точка входа, создание Flask-приложения
├── config.py               # Конфигурация
├── db.py                   # Подключение к SQLite, транзакции
├── db_init.py              # Схема БД, миграции, начальные данные
├── security.py             # Аутентификация, роли, CSRF, аудит
├── validators.py           # Валидация входных данных
├── backups.py              # Резервное копирование, HMAC, ротация
├── reports.py              # Построение отчётов
├── export.py               # Экспорт в PDF/XLSX
├── requirements.txt
├── blueprints/
│   ├── auth.py
│   ├── products.py
│   ├── stock.py
│   ├── hr.py
│   ├── finance.py
│   ├── admin.py
│   └── reports_bp.py
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── products.html
│   ├── receipts.html
│   ├── shipments.html
│   ├── writeoffs.html
│   ├── employees.html
│   ├── employee_edit.html
│   ├── shifts.html
│   ├── payroll.html
│   ├── finance.html
│   ├── users.html
│   ├── backups.html
│   ├── audit.html
│   ├── reports.html
│   ├── report_view.html
│   ├── change_password.html
│   └── error.html
├── static/
│   └── css/
│       └── style.css
└── tests/
    └── test_app.py
```

---

## Резервное копирование

- Бэкап создаётся через **SQLite Backup API** — это консистентный снимок БД.
- Каждый бэкап подписывается **HMAC-SHA256**; рядом с `.db` создаётся файл `.sig`.
- Старые бэкапы **ротируются**: хранится не более `MAX_BACKUPS` файлов.
- **Восстановление** возможно только при наличии и совпадении подписи.
- После восстановления сессия очищается — требуется повторный вход.
- **Ежедневный бэкап** создаётся автоматически при входе на главную страницу.
- Ручное создание и восстановление доступны администратору в разделе «Бэкапы».

---

## Отчёты и экспорт

Доступные отчёты:

- `stock` — остатки на складе;
- `profit` — финансовый отчёт по месяцам;
- `movements` — движения товаров.

Экспорт:

- **PDF** — через ReportLab;
- **XLSX** — через openpyxl.

При экспорте в Excel ячейки проходят санитизацию (защита от formula injection).

---

## Безопасность

В проекте реализованы:

- обязательный `SECRET_KEY`;
- CSRF-защита Flask-WTF;
- scrypt-хеширование паролей;
- защита от timing-атак при входе;
- rate limiting по `(username, ip)`;
- блокировка пользователей;
- разграничение доступа по ролям;
- HMAC-подпись бэкапов;
- защита от path traversal при восстановлении;
- проверка схемы SQLite перед восстановлением;
- аудит действий;
- безопасные session cookie;
- транзакции `BEGIN IMMEDIATE` для конкурентных операций.

---
