# Changelog — Hermes Agent Orchestration

## 2026-09-25

### Tenant isolation — восстановление после обновления v0.19.0
- Патч изоляции (`channel_profiles` → `disabled_toolsets` + MCP-изоляция + `tenant_name`) восстановлен в site-packages `gateway/run.py` — был стёрт обновлением от 22.07
- `check-gateway-patch.py` — watchdog переприменяет патч (`RUN_PY` → site-packages, исправлен баг отступа, полный патч с MCP)
- Cron-джоба `gateway-patch-watchdog` (every 10m, no_agent)
- `skill-tiers.yaml`: убраны 15 битых записей (71 → 56 base)
- Drift скиллов вычищен у тенантов (лишние → `skills.archived/`)
- `ddgs` установлен в системный python3 (веб-поиск у тенантов)

## 2026-08-09

### Apolaibot v3.0
- Shared chats: `/chat` в группах, inline-клавиатуры, UX-фичи
- Дедупликация кода, рефакторинг обработчиков
- Миграция на `hermes_config.py` (SSOT для ID)

## 2026-08-06

### OpenWiki
- 8 страниц документации: архитектура, workflows, конфигурация, тестирование

### GSC Audit
- `hermes_config.py` как SSOT для ID
- except:pass → logger, env var migration

## 2026-07-15

### Apolaibot security
- Scout audit: 2FA, IP whitelist, rate limit, input guard

## 2026-07-01

### Skill Sync v3
- Двухсторонняя синхронизация скиллов
- Трёхэтапное ревью
- Интеграция с профилями тенантов
