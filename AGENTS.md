# AGENTS.md — Hermes Orchestration

> Навигация для AI-агентов. Git-репозиторий оркестрации multi-tenant Hermes.

## Что это

Рабочий репозиторий конфигурации и скриптов оркестрации: три тенанта, изоляция профилей, боты, синхронизация скиллов, платёжные активаторы.

## Структура

```
hermes-orchestration/
├── bots/
│   ├── miropolbot.py        ← Morearbot (тенант-бот 1)
│   └── apolaibot-demo.py    ← Apolai (тенант-бот 2, demo)
├── configs/
│   ├── tenant-config.yaml   ← Конфигурация тенантов
│   └── skill-tiers.yaml     ← Уровни доступа к скиллам
├── scripts/
│   ├── skill-sync.py        ← Синхронизация скиллов между профилями
│   ├── stars-activator.py   ← Активатор Telegram Stars (Pro)
│   └── hermes-tenant        ← CLI для управления тенантами
├── docs/
│   ├── 01-infrastructure.md ← Инфраструктура
│   ├── 02-skill-sync.md     ← Синхронизация скиллов
│   ├── 03-constitution.md   ← Конституция оркестрации
│   ├── 05-onboarding-checklist.md ← Онбординг новых тенантов
│   └── 06-roadmap.md        ← План развития
└── README.md
```

## Архитектура

```
Море (default) ──полный доступ──▶ все toolsets, trading, cron
    │
    ├── Morearbot ──урезанный──▶ chat + /upgrade
    └── Apolai ────урезанный──▶ chat + /upgrade
```

## Как запускать

```bash
cd ~/hermes-orchestration

# Синхронизация скиллов
python3 scripts/skill-sync.py

# Активатор Telegram Stars
python3 scripts/stars-activator.py

# CLI управления тенантами
python3 scripts/hermes-tenant --help
```

## Ключевые файлы

| Файл | Назначение |
|------|-----------|
| `hermes_config.py` | **SSOT для ID.** ADMIN_IDS, UNLIMITED_USERS. Читает из env: `HERMES_ADMIN_IDS`, `HERMES_UNLIMITED_USERS`. Менять здесь, не в коде скриптов. |
| `configs/tenant-config.yaml` | Конфигурация тенантов (права, лимиты) |
| `configs/skill-tiers.yaml` | Уровни доступа: какие скиллы какому тенанту |
| `scripts/skill-sync.py` | Синхронизация скиллов default → тенанты |
| `scripts/stars-activator.py` | Активация Pro по оплате Telegram Stars |
| `bots/miropolbot.py` | Morearbot — основной тенант-бот |

## Инварианты

1. **Один гейтвей — две роли.** Не плодить отдельных гейтвеев для ботов.
2. **Изоляция через profiles.** Тенанты не видят чужих скиллов/памяти/кронов.
3. **Права через channel_profiles.** Не патчить код ботов для разграничения доступа.
4. **hermes_config.py — SSOT для ID.** Никогда не хардкодить ADMIN_ID/UNLIMITED_USERS в скриптах. Всегда импортировать из `hermes_config.py`.
- Документация в `docs/` на русском
- Основной источник правды: `~/.hermes/config.yaml`

## Инварианты

1. **Один гейтвей — две роли.** Не плодить отдельных гейтвеев для ботов.
2. **Изоляция через profiles.** Тенанты не видят чужих скиллов/памяти/кронов.
3. **Права через channel_profiles.** Не патчить код ботов для разграничения доступа.

## Критерии готовности

- [ ] `scripts/skill-sync.py` отрабатывает без ошибок
- [ ] Боты запускаются (`bots/miropolbot.py`, `bots/apolaibot-demo.py`)
- [ ] Конфиги валидны (YAML парсится)
