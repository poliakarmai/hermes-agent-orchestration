---
tags: [hermes, orchestration, architecture, master-doc]
created: 2026-06-16
updated: 2026-06-16
---

# Hermes Multi-Tenant Оркестрация — Полная Архитектура

## 1. Обзор

**Цель:** SaaS-платформа AI-ассистентов на базе Hermes Agent с изоляцией тенантов, биллингом через Telegram Stars и автоматическим онбордингом.

**Состояние:** 19/23 пунктов роадмапа ✅. 5 тенантов в проде.

---

## 2. Архитектура ботов

```
Пользователь
    │
    ├─ @Apolaibot (demo) ─── скрипт apolaibot-demo.py (86 строк, ~44 MB RAM)
    │   ├─ DeepSeek API напрямую
    │   ├─ Rate limiting: 30 RPM / 500 RPH
    │   ├─ Аудит-лог: tenant-audit.py
    │   └─ /upgrade → @miropolbot
    │
    ├─ @miropolbot (оплата) ── скрипт stars-payment-handler.py (~10 MB RAM)
    │   ├─ Telegram Stars: /start → invoice → оплата 100 ⭐
    │   ├─ Мгновенный онбординг: successful_payment → hermes-tenant onboard
    │   ├─ Алерт админу: «🎉 Новый клиент Pro!»
    │   └─ Уведомление клиенту: «Пиши /start в @Morearbot»
    │
    └─ @Morearbot (Pro) ──── Hermes Agent gateway (~230 MB RAM)
        ├─ Multi-tenant: изоляция через channel_profiles + Linux users
        ├─ DeepSeek API (deepseek-v4-pro)
        ├─ 44 скилла для тенантов (admin_only исключены)
        ├─ Obsidian vault для каждого тенанта
        └─ iptables-изоляция тенантов
```

### Systemd сервисы

| Сервис | RAM | Роль |
|--------|-----|------|
| `apolaibot-demo.service` | ~44 MB | Demo-бот для неприписанных |
| `miropolbot.service` | ~10 MB | Приём платежей Stars |
| `hermes-gateway.service` | ~230 MB | Продакшен-гейтвей для Pro-тенантов |
| `hermes-gateway-demo.service` | disabled | Старый, отключён (экономия 155 MB) |

---

## 3. Биллинг и подписки

### П платёжный флоу

```
Пользователь → @Apolaibot → /upgrade → @miropolbot → /start
    → Invoice (100 ⭐, 30 дней Pro)
    → Оплата Telegram Stars
    → stars-payment-handler.py:
        1. save_payment() → БД + мгновенный hermes-tenant onboard
        2. notify_admin() → алерт админу в DM
        3. tg_api sendMessage → «Пиши /start в @Morearbot»
        4. systemctl restart hermes-gateway
```

### Активация

| Компонент | Файл | Роль |
|-----------|------|------|
| П платёжный обработчик | `stars-payment-handler.py` | Принимает платежи, мгновенный онбординг |
| Активатор (cron fallback) | `stars-activator.py` | Каждые 2 мин проверяет неподтверждённые |
| Депровижнинг | `deprovision.py` | Каждые 30 мин отключает истекшие подписки |

### Таблица БД (`stars_payments.db`)

```sql
payments:     telegram_id, amount_stars, status, telegram_payment_id, expires_at
pro_users:    telegram_id, username, activated_at, expires_at, active
```

---

## 4. Изоляция тенантов

### Три слоя защиты

| Слой | Механизм | Что блокирует |
|------|----------|--------------|
| 1. Toolsets | `disabled_toolsets: [delegation, code_execution]` | Запуск кода, делегирование |
| 2. Каналы | `channel_profiles` + `channel_prompts` в config.yaml | Доступ к чужим сессиям |
| 3. Linux | Отдельный пользователь `hermes-<name>`, uid, iptables | Доступ к ФС, сеть |

### Что НЕ доступно тенантам

- `delegation` — не могут вызывать делегатов
- `code_execution` — не могут исполнять код
- `cronjob` — нет своих cron'ов
- `terminal` — нет прямого доступа к shell
- `memory-preload` + `obsidian-context` — admin_only, не видят Obsidian админа

### Что ДОСТУПНО тенантам

- 44 скилла из base-тира
- Obsidian vault в своей песочнице (`/home/hermes-<name>/obsidian-vault/`)
- Работа с API через свои ключи
- Веб-поиск
- Файлы в своей песочнице

---

## 5. Управление скиллами

### Тир-система (`config/skill-tiers.yaml`)

```
base:       44 скилла → синхронизируются всем тенантам
admin_only:  2 скилла (memory-preload, obsidian-context) → только админ
opt_in:      по запросу → админ устанавливает вручную
```

### Синхронизация (`skill-sync.py` v3)

Двухсторонняя:

```bash
# Админ → тенанты: синхронизация base-скиллов
python3 skill-sync.py

# Тенант → админ: обнаружить новые скиллы
python3 skill-sync.py --pull --tenant user_<tg_id>

# Импорт после ревью
python3 skill-sync.py --import <skill> --tenant user_<tg_id>
```

### 4-Stage Review Pipeline (CI/CD)

```
Stage 0: Validate (skill-validate.py)
    ├─ YAML frontmatter валидность
    ├─ Обязательные поля (name, description)
    ├─ Битые ссылки (references/, templates/, scripts/)
    ├─ Shell injection patterns (eval, exec, rm -rf)
    └─ Подозрительные пути (/home/, /root/, /etc/)

Stage 1: Security Scan (skill-security-scan.py)
    └─ CRITICAL findings → BLOCK

Stage 2: Judge Review (DeepSeek API)
    └─ Конституция, галлюцинации, читаемость

Stage 3: Adversarial Review (DeepSeek API, вторая модель)
    └─ Независимая проверка, JSON-вердикт
```

---

## 6. Управление тенантами

### `hermes-tenant` CLI

```bash
# Онбординг
hermes-tenant onboard --tg-id=123456789 --name=username

# Что делает:
# 1. Создаёт Linux-пользователя hermes-username
# 2. Настраивает iptables-изоляцию
# 3. Создаёт профиль Hermes (config.yaml, .env)
# 4. Добавляет channel_prompt + channel_profile
# 5. Добавляет tg_id в TELEGRAM_ALLOWED_USERS
# 6. Создаёт Obsidian vault
# 7. Устанавливает права (770)
# 8. Синхронизирует base-скиллы
# 9. Устанавливает rate limit tier = "pro"

# Офбординг
hermes-tenant offboard --tg-id=123456789

# Что делает:
# 1. Бэкап профиля (tar.gz)
# 2. Удаляет из channel_prompts/channel_profiles
# 3. Удаляет из TELEGRAM_ALLOWED_USERS
# 4. Удаляет iptables-правила
# 5. Удаляет Linux-пользователя
# 6. Удаляет профиль
# 7. Даунгрейдит rate limit → demo

# Список
hermes-tenant list
```

### Текущие тенанты

| TG ID | Имя | Профиль | Песочница | Статус |
|-------|-----|---------|-----------|--------|
| 319665243 | poliakarm | poliakarm | админ | 👑 |
| 470549555 | ilya | user_470549555 | /home/hermes-ilya | ✅ |
| 308591502 | cryptos | user_308591502 | /home/hermes-cryptos | ✅ |
| 2115597720 | kolesnikov | user_2115597720 | /home/hermes-kolesnikov | ✅ |
| 1148002325 | illarionov | user_1148002325 | /home/hermes-illarionov | ✅ |

---

## 7. Rate Limiting

### Система (`rate_limiter.py`)

Хранит лимиты в SQLite (`rate_limits.db`):

```sql
rate_limits:  tg_id, window_start, window_type (m/h), count
rate_config:  tg_id, tier, rpm_override, rph_override
```

### Тарифы

| Тариф | RPM | RPH | Где применяется |
|-------|-----|-----|----------------|
| Demo | 30 | 500 | apolaibot-demo.py |
| Pro | 60 | 2000 | Morearbot (Hermes gateway) |
| Admin | 120 | 5000 | без ограничений |

### Интеграция

- `apolaibot-demo.py` — проверка `can_proceed()` перед каждым сообщением
- `hermes-tenant onboard` — `rate_set_tier(tg_id, "pro")`
- `hermes-tenant offboard` — `rate_set_tier(tg_id, "demo")`
- `tenant-rate-watch.py` — cron каждые 15 мин, алерт админу при >80%

---

## 8. Мониторинг и Observability

### Дашборд (`generate-tenant-dashboard.py`)

Доступен: `http://2.27.48.142:8888/dashboard.html` (автообновление 30 сек)

**Показывает:**
- Summary: всего тенантов, Pro/Demo, запросы за 24ч, ошибки
- Карточки: @username, tg_id, тариф, подписка, дней осталось
- Rate usage: RPM/RPH с цветовой индикацией (зелёный/жёлтый/красный)
- Метрики: запросы, ошибки, latency (мс)
- Статус Obsidian vault

### Метрики (`metrics-collector.py`)

Собирает каждые 5 минут из логов gateway:
- Количество запросов на тенанта
- Количество ошибок
- Средняя latency (из логов Hermes)

Хранит в `tenant_metrics.db` с агрегацией по часам.

### Аудит-трейл (`tenant-audit.py`)

Логирует все действия тенантов:
- `apolaibot-demo.py` → логирует каждое сообщение
- `audit-log-parser.py` → парсит логи Hermes gateway каждые 5 мин

Хранит в `tenant_audit.db`. Очистка старше 90 дней.

### Алерты

| Watchdog | Частота | Что проверяет |
|----------|---------|--------------|
| `tenant-rate-watch.py` | 15 мин | Rate >80% → алерт админу |
| `deprovision.py` | 30 мин | Истекшие подписки → offboard + алерт |
| `metrics-collector.py` | 5 мин | Сбор latency/запросов |
| `audit-log-parser.py` | 5 мин | Парсинг логов gateway |

---

## 9. Бэкапы

### Авто-бэкап (`tenant-backup.py`)

Ежедневно в 02:00. Сохраняет в `~/.hermes/backups/daily/`:
- Все профили из `profiles/`
- `config.yaml`
- `stars_payments.db`

Ротация: хранит 7 последних бэкапов.

### Бэкап при офбординге

Автоматически создаётся `tar.gz` в `~/.hermes/backups/offboarded/` перед удалением профиля.

### Другие бэкапы

- `vpn-db-backup` — ежедневно 03:00 (VPN-бот БД)
- `vpn-snapshot` — ежедневно 02:55 (конфиги VPN)
- `system-backup-every-4-days` — каждые 4 дня (системные файлы)

---

## 10. Кроны (сводная таблица)

| Job ID | Имя | Расписание | Скрипт | no_agent |
|--------|-----|-----------|--------|----------|
| `806f7cfcbf7a` | stars-pro-activator | */2 мин | `stars-activator.py` | ✅ |
| `955c1aa18d3b` | pro-deprovision | */30 мин | `deprovision.py` | ✅ |
| `0f023c3d794c` | tenant-rate-watch | */15 мин | `tenant-rate-watch.py` | ✅ |
| `f81f8dd00d20` | tenant-dashboard | */15 мин | `generate-tenant-dashboard.py` | ✅ |
| `112f485a37d9` | audit-log-parser | */5 мин | `audit-log-parser.py` | ✅ |
| `8863c81896af` | audit-log-prune | 03:00 | `tenant-audit.py prune 90` | ✅ |
| `8a30ab04f72e` | tenant-daily-backup | 02:00 | `tenant-backup.py` | ✅ |
| `b26cdf67bf79` | metrics-collector | */5 мин | `metrics-collector.py` | ✅ |
| `d7902afb4ffc` | skill-sync | */3 дня | `skill-sync.py` | ❌ |
| `bb9fd1a92d3b` | daily-bollinger-scan | 10:00 | bybit-scan | ❌ |
| `ae067ee715cd` | scoring-scan | 11:00 | scoring scan | ❌ |
| `a97df6ed25f3` | утренний LONG | 05:00 | bybit-scan LONG | ❌ |
| `686dbf0e74e4` | M5/M3 авто-сканер | */4 часа | `m5m3-scanner.py` | ✅ |
| `68bcb500b54a` | cost-weekly | Пн 10:00 | cost tracking | ❌ |
| `c7dadf8c7661` | pnl-morning | 09:00 | PnL сводка | ❌ |
| `73609b3ad96a` | weekly-pnl | Пн 09:00 | `weekly-pnl.py` | ✅ |
| `7049e70d0967` | tenant-health-check | Пн 10:00 | `tenant-health-check.py` | ✅ |
| `7b18402a1b36` | system-backup | */4 дня | `system-backup.sh` | ✅ |
| `976c776393ec` | vpn-watch | */5 мин | `vpn-watch.py` | ✅ |

---

## 11. Файловая структура

```
~/.hermes/
├── config.yaml                    # Основной конфиг Hermes
├── .env                           # Токены (TELEGRAM_BOT_TOKEN, DEEPSEEK_API_KEY, etc.)
├── channel_profiles/              # Профили каналов (multi-tenant)
├── skills/                        # Base-скиллы (44 шт)
├── profiles/                      # Профили тенантов
│   ├── poliakarm/                 # Админский профиль
│   ├── user_470549555/            # Илья
│   ├── user_308591502/            # Cryptos
│   ├── user_2115597720/           # Колесников
│   └── user_1148002325/           # Илларионов
├── scripts/                       # Все скрипты оркестрации
│   ├── stars-payment-handler.py   # Miropolbot (платежи)
│   ├── stars-activator.py         # Активатор Pro
│   ├── deprovision.py             # Депровижнинг
│   ├── rate_limiter.py            # Rate limiting
│   ├── tenant-rate-watch.py       # Watchdog рейтов
│   ├── tenant-audit.py            # Аудит-лог
│   ├── audit-log-parser.py        # Парсер логов
│   ├── tenant-backup.py           # Бэкапы
│   ├── generate-tenant-dashboard.py # Дашборд
│   ├── metrics-collector.py       # Метрики
│   ├── skill-validate.py          # CI/CD валидация
│   └── skill-sync.py              # Синхронизация скиллов
├── data/
│   ├── stars_payments.db          # БД платежей
│   ├── rate_limits.db             # БД рейт-лимитов
│   ├── tenant_audit.db            # БД аудит-логов
│   ├── tenant_metrics.db          # БД метрик
│   └── dashboard.html             # HTML-дашборд
├── backups/
│   ├── daily/                     # Ежедневные бэкапы (ротация 7 дн)
│   └── offboarded/                # Бэкапы при офбординге
└── config/
    └── skill-tiers.yaml           # Тиры скиллов (base/admin_only/opt_in)
```

---

## 12. GitHub и Obsidian

### Репозиторий: `poliakarmai/hermes-agent-orchestration` (приватный)

```
docs/
├── 01-infrastructure.md           # Архитектура
├── 02-skill-sync.md               # Синхронизация скиллов
├── 03-constitution.md             # Конституция оркестрации
├── 05-onboarding-checklist.md     # Чек-лист онбординга
└── roadmap-orchestration.md       # Роадмап (этот документ)

scripts/                            # Все скрипты (9 шт)
bots/
├── apolaibot-demo.py              # Demo-бот
└── miropolbot.py                  # Платёжный бот
```

### Obsidian: `~/obsidian-vault/hermes/`

Ключевые заметки:
- `hermes-infra.md` — архитектура + таблица ботов
- `skill-sync-v3.md` — документирование синхронизации
- `roadmap-orchestration.md` — роадмап
- `00-Index.md` — индекс всех заметок

---

## 13. Roadmap

### ✅ Сделано (19/23)

Все пункты 1-19 реализованы и работают в проде.

### 🔜 Ближайшие

| # | Что | Приоритет |
|---|-----|-----------|
| 20 | Тест платёжного флоу (реальная оплата Stars) | 🥇 |
| 21 | Публичный лендинг + документация для продвижения | 🥈 |
| 22 | White-label: кастомные боты для B2B | 🥈 |
| 23 | Шардинг: горизонтальное масштабирование | 🥉 |

### Архитектурные решения (не пересматривать)

1. **Demo = вариант В** — лёгкий скрипт, не Hermes
2. **Продакшен = 1 гейтвей** — не плодить инстансы без шардинга
3. **Оплата = Telegram Stars** — не подключать внешние платёжки
4. **Изоляция = 3 слоя** — disabled_toolsets + channel_prompts + Linux users

### Метрики Q3 2026

- 20 активных тенантов
- Время онбординга: < 3 мин от оплаты до /start
- Uptime gateway: 99.5%
- Средний расход: < $0.03/день на тенанта
- 0 утечек данных между тенантами

---

## 14. Быстрый старт — шпаргалка

```bash
# Онбординг нового тенанта (вручную)
hermes-tenant onboard --tg-id=<ID> --name=<username>

# Офбординг
hermes-tenant offboard --tg-id=<ID>

# Список тенантов
hermes-tenant list

# Синхронизация скиллов
python3 ~/.hermes/scripts/skill-sync.py

# Проверить rate limits
python3 ~/.hermes/scripts/rate_limiter.py <tg_id>

# Дашборд
# Открыть: http://2.27.48.142:8888/dashboard.html

# Аудит-лог тенанта
python3 ~/.hermes/scripts/tenant-audit.py <tg_id>

# Статистика метрик
python3 ~/.hermes/scripts/metrics-collector.py summary
```
