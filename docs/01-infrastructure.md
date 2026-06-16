---
tags: [hermes, infra, multi-tenant]
---

# Hermes Infrastructure

## Версия
- v0.16.0 (upstream 56236b16)
- Streaming + typing indicator для Telegram

## Архитектурное решение (16.06.2026)
- **Demo-тенант → вариант В:** кастомный скрипт-бот (86 строк, DeepSeek API), без Hermes
- **Продакшен (Morearbot):** остаётся как есть — полноценный Hermes-гейтвей
- **Причина:** 90% лидам нужен только чат + /upgrade, незачем тащить MCP, терминал, 30 команд
- **Выгода:** минус один гейтвей → экономия RAM (~45MB vs ~200MB), нет polling-конфликтов при рестарте

### Цепочка ботов (16.06.2026)
```
Пользователь → @Apolaibot (demo, 45MB) → /upgrade
                                            → @miropolbot (оплата Stars, 10MB)
                                            → авто-онбординг (stars-activator, cron 2min)
                                            → @Morearbot (полный Hermes, 200MB)
```

| Бот | Тип | RAM | Функция |
|-----|-----|-----|---------|
| @Apolaibot | Скрипт (python-telegram-bot) | ~45MB | Демо: чат + /upgrade |
| @miropolbot | Скрипт (polling) | ~10MB | Оплата Telegram Stars |
| @Morearbot | Hermes Gateway | ~200MB | Полный доступ (Pro) |

**Скрипты:**
- `~/.local/bin/apolaibot-demo.py` — demo-бот, 86 строк
- `~/.hermes/scripts/stars-payment-handler.py` — приём платежей
- `~/.hermes/scripts/stars-activator.py` — авто-онбординг (вызывает `hermes-tenant onboard`)
- `~/.config/systemd/user/apolaibot-demo.service` — systemd-юнит
- `~/.config/systemd/user/stars-payment.service` — systemd-юнит
- `~/.hermes/profiles/demo/` — профиль demo-бота (.env, config.yaml)

**Cron:** `stars-pro-activator` (каждые 2 мин, no_agent) — проверяет БД платежей → `hermes-tenant onboard` → рестарт gateway

## Multi-tenant
- ОДИН агент, ОДИН бот, ОДИН процесс (продакшен)
- Роутинг: channel_prompts + channel_profiles в config.yaml
- Профили в ~/.hermes/profiles/<name>/
- Общие скиллы: /opt/hermes/shared-skills/

## Патч gateway/run.py (06.06.2026)
- profile-specific disabled_toolsets
- Файл: ~/.hermes/hermes-agent/gateway/run.py
- Строка: "profile-specific disabled_toolsets"
- При обновлении Hermes может слететь — переприменить

## Cron
- Canary-watch: раз в 12ч, silent
- Cost-tracking: pnl-morning 09:00, cost-weekly пн 10:00
- GitHub push: пн 10:00
- tenant-health-check

## Профили
- default (Поляков) — полный доступ
- user_470549555 (Илья) — disabled: delegation, code_execution
