#!/usr/bin/env python3
"""AEGIS Demo Bot - Telegram bot on OpenAI-compatible API. Replaces Hermes gateway for @Apolaibot."""

import os, sys, json, logging, aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get("TELEGRAM_" + "BOT_TOKEN", "")
if not TOKEN:
    print("FATAL: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
    sys.exit(1)

API_URL = os.environ.get("APOLAIBOT_API_URL", "https://api.deepseek.com/v1")
API_KEY = os.environ.get("APOLAIBOT_API_KEY", os.environ.get("DEEPSEEK_API_KEY", ""))
MODEL = os.environ.get("APOLAIBOT_MODEL", "deepseek-chat")
if not API_KEY:
    print("FATAL: neither APOLAIBOT_API_KEY nor DEEPSEEK_API_KEY set", file=sys.stderr)
    sys.exit(1)

SYSTEM_PROMPT = """You are Aegis AI Engine - a demo AI assistant showing capabilities to new users.
Rules: concise, friendly answers. No Hermes commands. Answer in the user's language. Suggest /upgrade for full version questions."""

conversations = {}
MAX_HISTORY = 20

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("apolaibot-demo")

async def chat_completion(chat_id, user_msg):
    if chat_id not in conversations:
        conversations[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    conversations[chat_id].append({"role": "user", "content": user_msg})
    if len(conversations[chat_id]) > MAX_HISTORY + 1:
        conversations[chat_id] = [conversations[chat_id][0]] + conversations[chat_id][-(MAX_HISTORY):]
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}", "Accept-Encoding": "gzip"}
    payload = {"model": MODEL, "messages": conversations[chat_id], "temperature": 0.7, "max_tokens": 1500}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_URL}/chat/completions", headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    logger.error(f"API error {resp.status}")
                    return "Sorry, service temporarily unavailable."
                data = await resp.json()
                reply = data["choices"][0]["message"]["content"]
                conversations[chat_id].append({"role": "assistant", "content": reply})
                return reply
    except Exception as e:
        logger.error(f"API error: {e}")
        return "Unable to reach AI. Try later."

async def cmd_start(update, context):
    await update.message.reply_markdown(
        f"Hello, {update.effective_user.first_name}!\n\n"
        "I am **Aegis AI Engine** -- demo AI assistant.\n\n"
        "/upgrade for full version info.\nJust ask me anything!"
    )

async def cmd_upgrade(update, context):
    await update.message.reply_markdown(
        "🚀 **Aegis AI Engine Pro** — 200₽/мес (~100 ⭐)\n\n"
        "Полный доступ: 154+ скиллов, trading, безлимитный контекст, kernel-level изоляция.\n\n"
        "Для оплаты перейди в [@miropolbot](https://t.me/miropolbot) → /start\n"
        "После оплаты подписка активируется автоматически — просто напиши /start в @Morearbot."
    )

async def handle_message(update, context):
    msg = update.message.text
    if not msg or not msg.strip():
        return
    chat_id = update.effective_chat.id
    logger.info(f"[chat={chat_id}] {msg[:100]}")
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    reply = await chat_completion(chat_id, msg)
    await update.message.reply_markdown(reply)

async def error_handler(update, context):
    logger.error(f"Error: {context.error}")

def main():
    logger.info(f"Starting apolaibot-demo (model={MODEL}, api={API_URL})")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("upgrade", cmd_upgrade))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    logger.info("Bot polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
