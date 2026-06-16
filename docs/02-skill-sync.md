---
tags: [hermes, skills, sync, multi-tenant]
created: 2026-06-16
---

# Skill Sync v3 — Двухсторонняя синхронизация скиллов

## Концепция

Skill Sync v3 позволяет не только раздавать скиллы админа всем тенантам, но и **принимать доработанные скиллы от тенантов обратно** — с трёхэтапной проверкой безопасности и качества.

## Поток данных

```
Admin (base) ──sync──→ Все тенанты (base skills)
                            ↓
   Tenant дорабатывает скилл → skills.local/
                            ↓
   Admin: skill-sync.py --pull --tenant <name>
                            ↓
   Трёхэтапное ревью (security → judge → adversarial)
                            ↓
   Admin: skill-sync.py --import <skill> --tenant <name>
                            ↓
   Скилл → base → sync всем тенантам
```

## Команды

| Команда | Назначение |
|---------|-----------|
| `python3 skill-sync.py` | Синхронизация base → все тенанты |
| `python3 skill-sync.py --dry-run` | Превью без изменений |
| `python3 skill-sync.py --status` | Статус всех тенантов |
| `python3 skill-sync.py --install <skill> --tenant <name>` | Установить opt-in скилл тенанту |
| `python3 skill-sync.py --pull --tenant <name>` | Обнаружить + проверить скиллы тенанта |
| `python3 skill-sync.py --pull --tenant <name> --dry-run` | Превью без ревью |
| `python3 skill-sync.py --import <skill> --tenant <name>` | Импорт в base + sync всем |

## Трёхэтапное ревью

### Stage 1: Security Scan 🔒
- **Инструмент:** `skill-security-scan.py`
- **Что проверяет:** инъекции, опасные команды, валидность YAML
- **Критерий блокировки:** CRITICAL-находки

### Stage 2: Judge Review ⚖️
- **Инструмент:** `~/.local/bin/judge` (DeepSeek API)
- **Что проверяет:** соответствие конституции Hermes, безопасность периметра
- **Критерий блокировки:** `passed: false`

### Stage 3: Adversarial Review 🧠
- **Инструмент:** DeepSeek API (вторая модель, независимая оценка)
- **Что проверяет:**
  1. Не противоречит ли конституции? (user sovereignty, safety, scope discipline)
  2. Нет ли галлюцинаций в командах/путях?
  3. Понятны ли инструкции?
  4. Безопасен ли для multi-tenant?
- **Критерий блокировки:** `approved: false`, score < порога

## Безопасность

- **При импорте — повторное ревью.** Нельзя обойти проверку, вызвав `--import` сразу.
- **После импорта** локальная копия → `skills.imported/` (архив, не удаляется)
- **Tiers:** импортированный скилл автоматически → `base` tier → доступен всем
- **Локальные оверрайды** (`skills.local/`) никогда не затираются при sync

## Расположение

```
~/.hermes/
├── skills/                              ← BASE (source of truth)
├── config/skill-tiers.yaml              ← tiers: base / admin_only / opt_in
├── scripts/skill-sync.py                ← движок синхронизации (v3)
├── scripts/skill-security-scan.py       ← сканер безопасности
└── profiles/
    └── <tenant>/
        ├── skills/                      ← auto-synced (base skills)
        ├── skills.local/                ← tenant modifications (never overwritten)
        └── skills.imported/             ← archive of imported skills
```

## Пример использования

```bash
# Илья доработал скилл "custom-analysis" → положил в skills.local/

# 1. Обнаружить и проверить
python3 ~/.hermes/scripts/skill-sync.py --pull --tenant user_470549555

# Вывод:
# 🔍 Found 1 skill(s) from user_470549555:
#   🆕 new  custom-analysis  (3,421 bytes)
# 
# 📋 Review pipeline:
#   📄 custom-analysis:
#     🔒 Stage 1/3: Security scan...
#       ✅ Passed
#     ⚖️  Stage 2/3: Judge review...
#       ✅ Passed
#     🧠 Stage 3/3: Adversarial review...
#       ✅ All stages passed
# 
# ✅ 1 skill(s) passed review. Ready to import:
#   • custom-analysis

# 2. Импортировать
python3 ~/.hermes/scripts/skill-sync.py --import custom-analysis --tenant user_470549555
# → в base + всем тенантам
```

## Связанные заметки

- [[hermes-infra]] — общая инфраструктура
- [[Оркестрация-Hermes]] — полное описание оркестрации
- [[orchestration-improvements-v2]] — 5 улучшений оркестрации
