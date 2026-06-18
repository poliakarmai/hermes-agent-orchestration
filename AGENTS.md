# AGENTS.md — Hermes Agent Orchestration (Git)

> Навигация для AI-агентов. Git-репозиторий с документацией и скриптами оркестрации.

## Что это

Git-репозиторий (`~/projects/hermes-agent-orchestration`) с документацией, планами и скриптами оркестрации Hermes.  
Зеркало Obsidian-заметок по оркестрации, плюс исполняемые скрипты.

## Структура

```
projects/hermes-agent-orchestration/
├── docs/
│   ├── orchestration-master.md          ← Главный документ по оркестрации
│   ├── roadmap-orchestration.md         ← Roadmap
│   ├── kaggle-ai-agents-course.md       ← Заметки по Kaggle-курсу
│   └── aegis-landing.html               ← Лендинг Aegis
└── scripts/
    ├── deepseek-balance-monitor.py      ← Монитор баланса DeepSeek API
    ├── rate_limiter.py                  ← Rate limiter
    ├── skill-sync.py                    ← Синхронизация скиллов
    ├── skill-validate.py                ← Валидация скиллов
    ├── metrics-collector.py             ← Сбор метрик
    ├── tenant-backup.py                 ← Бэкап тенантов
    └── generate-tenant-dashboard.py     ← Дашборд тенантов
```

## Ключевые скрипты

| Скрипт | Назначение |
|--------|-----------|
| `skill-sync.py` | Синхронизация скиллов между профилями |
| `skill-validate.py` | Валидация SKILL.md (YAML, структура) |
| `metrics-collector.py` | Сбор метрик использования скиллов |
| `tenant-backup.py` | Бэкап профилей тенантов |
| `deepseek-balance-monitor.py` | Мониторинг баланса DeepSeek API |
| `rate_limiter.py` | Rate limiting для API-запросов |

## Как запускать

```bash
cd ~/projects/hermes-agent-orchestration

# Синхронизация скиллов
python3 scripts/skill-sync.py

# Валидация скиллов
python3 scripts/skill-validate.py

# Бэкап тенантов
python3 scripts/tenant-backup.py

# Дашборд
python3 scripts/generate-tenant-dashboard.py
```

## Конвенции

- Git-репозиторий, ветка `master`
- Документация в `docs/` на русском
- Скрипты в `scripts/` с Python 3.11+
- Зеркалирует Obsidian vault (основной источник — `obsidian-vault/hermes/`)

## Инварианты

1. **Obsidian — основной источник.** Этот репозиторий — зеркало, не наоборот.
2. **Скрипты идемпотентны.** Повторный запуск не должен ломать состояние.
3. **Не редактировать прод-конфиги напрямую.** Все изменения через скрипты синхронизации.

## Критерии готовности

- [ ] `python3 scripts/skill-sync.py` — без ошибок
- [ ] `python3 scripts/tenant-backup.py` — создаёт бэкап
- [ ] `python3 scripts/generate-tenant-dashboard.py` — генерит дашборд
- [ ] Git clean: все изменения закоммичены или в `.gitignore`
