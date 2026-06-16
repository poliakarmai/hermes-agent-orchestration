# Hermes Agent Orchestration

Приватный репозиторий оркестрации AI-агентов платформы Hermes.

## Архитектура

Один процесс Hermes — много пользователей. Изоляция на трёх слоях:

| Слой | Механизм | Эффект |
|------|----------|--------|
| Инструменты | `disabled_toolsets` из профиля | tenant не может spawn'ить агентов, ставить cron, execute_code |
| Промпты | `channel_prompts` с песочницей | LLM знает свою песочницу и чужие границы |
| Файлы | Linux-пользователи + chmod 770 | Процесс Hermes имеет доступ, другие тенанты — нет |

## Цепочка ботов

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

## Структура репо

```
docs/           — архитектурная документация
bots/           — исходники ботов (apolaibot, miropolbot)
scripts/        — скрипты оркестрации (skill-sync, stars-activator, hermes-tenant)
configs/        — примеры конфигов профилей
```

## Ключевые фичи

- **Skill Sync v3** — двухсторонняя синхронизация скиллов с трёхэтапным ревью
- **Auto-onboarding** — `hermes-tenant onboard` одной командой
- **Stars Payment** — приём оплаты Telegram Stars → авто-активация Pro
- **Kernel-level Isolation** — Linux-песочницы, iptables для каждого тенанта
- **Per-user Cost Tracking** — учёт расходов на API

## Стек

- **LLM:** DeepSeek V4 Pro
- **Gateway:** Hermes Agent (Nous Research)
- **Инфра:** Linux (systemd user-level), Python 3.11
- **Платежи:** Telegram Stars (XTR)
- **Память:** Obsidian vault (per-tenant)

## Статус (июнь 2026)

- ✅ 5 тенантов в проде
- ✅ Авто-онбординг + оплата Stars
- ✅ Демо-бот → Pro-воронка
- 🔜 Публичное продвижение
