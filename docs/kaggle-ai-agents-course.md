---
tags: [kaggle, ai-agents, vibe-coding, course]
created: 2026-06-16
source: "Kaggle 5-Day AI Agents: Intensive Vibe Coding Course With Google (June 15-19, 2026)"
---

# Kaggle AI Agents Course — Конспект

Курс от Google + Kaggle: 5 дней, с 15 по 19 июня 2026. Бесплатно.
Записался: Poliakarm (Armyanao@gmail.com).

## Day 1: Introduction to Agents & Vibe Coding

**Whitepaper:** «The New SDLC with Vibe Coding» (Addy Osmani, Shubham Saboo, Sokratis Kartakis)

### Ключевые идеи

1. **Vibe Coding vs Agentic Engineering — спектр, не бинарность**
   - Vibe coding: «напиши мне приложение для X» — полное доверие AI
   - Agentic engineering: структура, верификация, гарды вокруг AI
   - Разница — в количестве структуры и человеческого суждения

2. **Factory Model (Модель фабрики)**
   - Главный продукт разработчика — не код, а **система, производящая код**
   - Спецификации → агенты → тесты → feedback loops → guardrails
   - Разработчик = управляющий фабрикой, не сборщик на конвейере

3. **Agent = Model + Harness**
   - Модель ≠ система. Это ловушка.
   - Harness = evaluation, constraints, context, tools, guardrails
   - На Terminal Bench 2.0 команда подняла агента из топ-30 в топ-5, изменив **только harness**, не трогая модель
   - Когда агент ошибается → первая мысль «виновата модель», но чаще проблема в harness'е

4. **Context Engineering > Prompt Engineering**
   - Качество AI-кода зависит от качества контекста, а не от хитрости промпта
   - 6 типов контекста: instructions, knowledge, memory, examples, tools, guardrails
   - Static vs dynamic context — архитектурное решение первого класса

5. **Conductor vs Orchestrator**
   - Conductor: направляешь AI в реальном времени (IDE)
   - Orchestrator: ставишь цели, агенты работают параллельно, ты review'ишь асинхронно
   - Навыки смещаются: syntax expertise → specification, decomposition, evaluation, system design

6. **The 80% Problem**
   - AI генерит 80% кода за минуты
   - Оставшиеся 20% требуют глубокого контекста
   - Ошибки AI эволюционировали: от синтаксических → к концептуальным (выглядит правильно, тесты проходит, но логика неверна)

7. **Экономика**
   - Vibe coding: дёшево на старте, дорого в обслуживании (token burn, inconsistent code, security debt)
   - Agentic engineering: дороже upfront (specs, evals, context design), но радикально дешевле на масштабе

> **Главный вывод: «Generation is solved. Verification, judgment and direction are the new craft.»**

---

## Day 2: Agent Tools & Interoperability

**Whitepaper:** «Agent Tools & Interoperability with MCP» (Mike Styer, Kanchana Patlolla, et al.)

### Ключевые идеи

1. **Tools = глаза и руки агента**
   - Foundation models без тулов — просто генераторы текста
   - Инструменты позволяют агенту воспринимать мир и действовать
   - Вызов: N×M проблема интеграций (N моделей × M инструментов)

2. **Model Context Protocol (MCP)**
   - Открытый стандарт (с 2024) для подключения инструментов к моделям
   - Решает N×M проблему: один протокол для всех
   - Компоненты: servers, resources, tools, prompts
   - Ключевой риск: безопасность при подключении к enterprise-системам

3. **A2A (Agent-to-Agent)**
   - Протокол коллаборации агентов
   - Агенты общаются друг с другом без человека в loop'е

4. **A2UI (Agent-to-User Interface)**
   - Генеративный UI: агент сам создаёт интерфейс под задачу

5. **AP2 / UCP (Agent Payments / Universal Commerce Protocol)**
   - Машинные платежи: агенты платят друг другу за сервисы
   - Новая экономика agent-to-agent commerce

6. **Enterprise MCP Security**
   - Главный вызов: MCP открывает доступ к чувствительным системам
   - Нужны: sandboxing, permission scoping, audit logging
   - Без этого MCP в проде = дыра в безопасности

> **Главный вывод: MCP решает проблему N×M интеграций, но enterprise-readiness требует серьёзной работы над безопасностью.**

---

## Практические инструменты курса

### Antigravity 2.0
- Среда разработки от Google для AI-агентов
- IDE + CLI
- Встроенная поддержка MCP серверов
- Skills: переиспользуемые компоненты для агентов

### Google AI Studio
- Визуальная среда для создания AI-приложений
- Деплой на Cloud Run в один клик

### Antigravity CLI
- Терминальный интерфейс для vibe coding
- Позволяет создавать, тестировать и деплоить агентов из командной строки

---

## Что применимо к Hermes

| Концепт из курса | Как применимо к Hermes |
|-----------------|----------------------|
| Factory Model | Ты уже это делаешь: Hermes = фабрика, ты — управляющий |
| Agent = Model + Harness | Наш harness: Hermes конституция, skill-sync, CI/CD, rate limiting |
| Context Engineering | Твои channel_prompts, Obsidian vault, memory — это и есть context engineering |
| Orchestrator pattern | `delegate_task`, cron-агенты — ты оркестратор |
| 80% Problem | Skill-validate.py + security scan — наша защита от «правдоподобных» ошибок |
| MCP Security | Твоя 3-слойная изоляция (toolsets + Linux + iptables) — это enterprise MCP security на практике |
| Conductor vs Orchestrator | Ты в режиме Orchestrator: ставишь цели мне и cron'ам, review'ишь результат |

---

## План на оставшиеся дни

| День | Дата | Тема |
|------|------|------|
| Day 3 | 17 июня | (ожидается) |
| Day 4 | 18 июня | (ожидается) |
| Day 5 | 19 июня | Capstone project |
