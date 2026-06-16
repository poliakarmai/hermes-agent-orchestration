---
tags: [hermes, memory]
updated: 2026-06-09
---

# Техническая память

## LLM & Инструменты
- DeepSeek V4 Pro (deepseek-v4-pro) для всех вызовов. deepseek-chat — старая версия.
- Judge: прямой вызов DeepSeek API, max_tokens=2000, timeout=30с. exit 0=passed.
- FreeLLMAPI: ~/freellmapi, port 3001, systemd. Unified key. HF(id=1)+OR(id=2).
- Muapi.ai: ключ da68e5b0..., POST /api/v1/flux-dev-image, $0.015/img.
- TTS: всегда русский, голос Дмитрий (ru-RU-DmitryNeural).
- Эволюция скиллов: ~/hermes-agent-self-evolution, venv .venv (py3.11), dspy+gepa+optuna.

## Сервер
- Хельсинки, Финляндия (2.27.48.142, ISP Netshield LTD)
- 1.9GB RAM (НЕ 64GB!), своп 2GB — критично экономить память
- Все systemd-сервисы — user-level: юниты в ~/.config/systemd/user/
- При запуске bybit raw: всегда `HOME=/home/openclaw` (падает без этого)

## Отправка файлов
- MEDIA-теги и hermes send --file НЕ работают для вложений
- Использовать прямой вызов Telegram Bot API (sendDocument)
- chat_id=319665243 (Poliakarm), НЕ 5529208670 (Cryptos)

## Cron-скрипты
- no_agent: stdout = канал доставки, никогда не вызывать send_alert()/hermes send
- Хрон использует ~/.hermes/scripts/ (проверять оба пути если скрипт в ~/.local/bin/)
- Тишина когда всё работает. Silent when OK, alert when broken.

## Безопасность
- .env: age-шифрование (age1dcvtdya3t...), ключ ~/.hermes/keys/hermes.key (600)
- decrypt_env.py как ExecStartPre в openclaw.service

## Правила пользователя
- Не слать approved-запросы — исполнять без подтверждений
- GitHub push только через cron github-weekly-push (пн 10:00), не вручную
- Торговые правила — в [[trading]] и скилле `bybit-trading`, здесь не дублируются

## Онбординг новых клиентов — ОБЯЗАТЕЛЬНАЯ ПРОВЕРКА
После `hermes-tenant onboard` всегда проверять три места:
1. `TELEGRAM_ALLOWED_USERS` в `~/.hermes/.env` — добавить новый tg_id (иначе gateway шлёт «Unauthorized user»)
2. `channel_profiles` в `config.yaml` — маппинг tg_id → профиль
3. `channel_prompts` в `config.yaml` — системный промпт для tg_id
4. После всех правок — `systemctl --user restart hermes-gateway`
   ⚠️ Рестарт может занять 3+ минуты из-за graceful shutdown текущих сессий.
   Проверять: `systemctl --user status hermes-gateway | grep Active`
   Прецедент: 16.06.2026 Колесников (2115597720) не мог писать — TELEGRAM_ALLOWED_USERS не обновлён.
