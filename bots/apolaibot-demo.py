#!/usr/bin/env python3
"""AEGIS Demo Bot — Telegram AI Chat. v3.0 (shared chats + UX features)."""

import os, sys, json, logging, aiohttp, re, time, ssl, io
from pathlib import Path
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes,
)
from telegram.constants import ChatType

# ── Env ──────────────────────────────────────────────
def _load_env(path=None):
    if path is None:
        path = os.path.expanduser("~/.hermes/profiles/demo/.env")
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        print(f"WARNING: .env not found at {path}", file=sys.stderr)
    return env

_env = _load_env()
TOKEN   = _env.get("TELEGRAM_BOT_TOKEN", "")
API_URL = _env.get("APOLAIBOT_API_URL", os.environ.get("APOLAIBOT_API_URL", "https://api.deepseek.com/v1"))
API_KEY = _env.get("DEEPSEEK_API_KEY", _env.get("APOLAIBOT_API_KEY", ""))
MODEL   = _env.get("APOLAIBOT_MODEL", os.environ.get("APOLAIBOT_MODEL", "deepseek-chat"))

for var, name in [(TOKEN, "TELEGRAM_BOT_TOKEN"), (API_KEY, "DEEPSEEK_API_KEY")]:
    if not var:
        print(f"FATAL: {name} not set", file=sys.stderr); sys.exit(1)

SYSTEM_PROMPT = (
    "You are Aegis AI Engine — a demo AI assistant showing capabilities to new users.\n"
    "Rules: concise, friendly answers. No Hermes commands. Answer in the user's language.\n"
    "Suggest /upgrade for full version questions."
)

# ── Globals ──────────────────────────────────────────
conversations  = {}          # {chat_id: {messages: [...], _ts: float}}
incognito_chats = set()      # chat_ids with persistence disabled
MAX_HISTORY    = 20
BOT_USERNAME   = None
FEEDBACK_FILE  = Path(os.path.expanduser("~/.local/share/apolaibot/feedback.jsonl"))

STATE_DIR  = Path(os.environ.get("APOLAIBOT_STATE_DIR", os.path.expanduser("~/.local/share/apolaibot")))
STATE_FILE = STATE_DIR / "conversations.json"
STATE_TTL  = 86400 * 7

INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|messages?)",
    r"(?i)you\s+are\s+now\s+(DAN|STAN|jailbreak)",
    r"(?i)pretend\s+(you\s+are|to\s+be)\s",
    r"(?i)new\s+system\s+prompt",
    r"(?i)forget\s+(everything|your\s+training)",
    r"(?i)developer\s+mode",
    r"(?i)override\s+(system|safety|instructions)",
]

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("apolaibot-demo")

_SSL_CONTEXT = ssl.create_default_context()
_SSL_CONTEXT.check_hostname = True
_SSL_CONTEXT.verify_mode = ssl.CERT_REQUIRED

# ── Helpers ──────────────────────────────────────────
def _sanitize_input(text: str) -> str:
    if not text or len(text) > 8000:
        return text[:8000] if text else ""
    for pat in INJECTION_PATTERNS:
        if re.search(pat, text):
            logger.warning(f"Injection blocked: {text[:100]}")
            return "[blocked]"
    return text

def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            now = time.time()
            return {k: v for k, v in data.items() if isinstance(v, dict) and v.get("_ts", 0) > now - STATE_TTL}
    except Exception as e:
        logger.warning(f"Load state failed: {e}")
    return {}

def _save_state():
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = str(STATE_FILE) + ".tmp"
        with open(tmp, "w") as f:
            json.dump({k: v for k, v in conversations.items() if k not in incognito_chats}, f)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        logger.warning(f"Save state failed: {e}")

def _is_bot_mentioned(text: str, entities) -> bool:
    if not text or not BOT_USERNAME:
        return False
    if entities:
        for ent in entities:
            if ent.type == "mention":
                mention = text[ent.offset:ent.offset + ent.length]
                if mention.lower() == f"@{BOT_USERNAME.lower()}":
                    return True
    return text.strip().lower().startswith(f"@{BOT_USERNAME.lower()}")

def _strip_mention(text: str) -> str:
    if not text or not BOT_USERNAME:
        return text
    for pat in [
        re.compile(rf"^@{re.escape(BOT_USERNAME)}\s*,?\s*", re.IGNORECASE),
        re.compile(rf"^@{re.escape(BOT_USERNAME)}$", re.IGNORECASE),
    ]:
        text = pat.sub("", text).strip()
    return text

def _detect_lang(text: str) -> str:
    """Quick lang detect: count Cyrillic vs Latin chars."""
    cyr = sum(1 for c in text if 'а' <= c.lower() <= 'я' or c.lower() == 'ё')
    return "ru" if cyr > len(text) * 0.3 else "en"

def _log_feedback(chat_id: int, vote: str):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(FEEDBACK_FILE, "a") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "chat": chat_id, "vote": vote}) + "\n")
    except Exception:
        pass

def _build_feedback_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("👍", callback_data="fb_up"),
        InlineKeyboardButton("👎", callback_data="fb_down"),
    ]])

# ── LLM ──────────────────────────────────────────────
async def chat_completion(chat_id, user_msg, system_override: str | None = None):
    is_incognito = chat_id in incognito_chats
    cache_key = f"incog_{chat_id}" if is_incognito else str(chat_id)

    if cache_key not in conversations:
        conversations[cache_key] = {
            "messages": [{"role": "system", "content": system_override or SYSTEM_PROMPT}],
            "_ts": time.time(),
        }
    conversations[cache_key]["messages"].append({"role": "user", "content": user_msg})
    conversations[cache_key]["_ts"] = time.time()
    msgs = conversations[cache_key]["messages"]
    if len(msgs) > MAX_HISTORY + 1:
        conversations[cache_key]["messages"] = [msgs[0]] + msgs[-(MAX_HISTORY):]

    api_messages = [m for m in conversations[cache_key]["messages"] if isinstance(m, dict) and "role" in m]
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    payload = {"model": MODEL, "messages": api_messages, "temperature": 0.7, "max_tokens": 1500}

    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=_SSL_CONTEXT)) as s:
            async with s.post(f"{API_URL}/chat/completions", headers=headers, json=payload,
                              timeout=aiohttp.ClientTimeout(total=60)) as r:
                if r.status != 200:
                    logger.error(f"API {r.status}")
                    return "Sorry, service temporarily unavailable."
                data = await r.json()
                reply = data["choices"][0]["message"]["content"]
                conversations[cache_key]["messages"].append({"role": "assistant", "content": reply})
                if not is_incognito:
                    _save_state()
                return reply
    except Exception as e:
        logger.error(f"API: {e}")
        return "Unable to reach AI. Try later."

# ── Commands ─────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_markdown(
        f"Hello, {name}! 👋\n\n"
        f"I'm **Aegis AI Engine** — demo AI assistant with 150+ skills.\n\n"
        f"🚀 /upgrade — Pro version with unlimited features\n"
        f"💬 /incognito — private mode (no history saved)\n"
        f"📝 /summarize — condense the conversation\n"
        f"📤 /export — download chat history\n"
        f"🌐 /language — switch EN/RU\n\n"
        f"Just ask me anything!"
    )

async def cmd_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = "en"
    if update.message and update.message.text:
        # Try to detect from user history if available
        pass
    await update.message.reply_markdown(
        "🚀 **Aegis AI Engine Pro**\n\n"
        "**$5/month (~100 Telegram Stars)**\n\n"
        "▸ Full Hermes gateway access\n"
        "▸ 150+ professional skills\n"
        "▸ Trading, VPN, automation\n"
        "▸ Unlimited context\n"
        "▸ Kernel-level isolation\n\n"
        "📲 Pay via [@miropolbot](https://t.me/miropolbot) → /start\n"
        "After payment — /start in [@Morearbot](https://t.me/Morearbot)"
    )

async def cmd_incognito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in incognito_chats:
        incognito_chats.discard(chat_id)
        await update.message.reply_markdown("🟢 **Normal mode** — history is saved again.")
    else:
        incognito_chats.add(chat_id)
        await update.message.reply_markdown("🕶️ **Incognito mode** — this conversation won't be saved.\n/normal to exit.")

async def cmd_normal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    incognito_chats.discard(chat_id)
    await update.message.reply_markdown("🟢 Back to normal mode.")

async def cmd_summarize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    is_incognito = update.effective_chat.id in incognito_chats
    cache_key = f"incog_{chat_id}" if is_incognito else chat_id

    if cache_key not in conversations or len(conversations[cache_key].get("messages", [])) <= 2:
        await update.message.reply_markdown("Nothing to summarize yet. Chat with me first!")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Build history text
    msgs = [m for m in conversations[cache_key]["messages"] if m["role"] in ("user", "assistant")]
    history = "\n".join(f"{'🧑' if m['role'] == 'user' else '🤖'}: {m['content']}" for m in msgs[-20:])

    summary_prompt = (
        "Summarize this conversation in 3-5 bullet points. "
        "Keep key decisions, facts, and action items. Be concise.\n\n"
        f"{history}"
    )

    reply = await chat_completion(
        update.effective_chat.id, summary_prompt,
        system_override="You are a summarizer. Return ONLY bullet points, no preamble.",
    )
    await update.message.reply_markdown(f"📝 **Conversation Summary**\n\n{reply}", reply_markup=_build_feedback_kb())

async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    is_incognito = update.effective_chat.id in incognito_chats
    cache_key = f"incog_{chat_id}" if is_incognito else chat_id

    if cache_key not in conversations or len(conversations[cache_key].get("messages", [])) <= 2:
        await update.message.reply_markdown("Nothing to export yet.")
        return

    msgs = [m for m in conversations[cache_key]["messages"] if m["role"] in ("user", "assistant")]
    lines = [f"# AEGIS Chat Export — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
    for m in msgs:
        role = "YOU" if m["role"] == "user" else "AEGIS"
        lines.append(f"\n## {role}\n{m['content']}\n")

    buf = io.BytesIO("\n".join(lines).encode("utf-8"))
    buf.name = f"aegis_chat_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    await update.message.reply_document(buf, caption="📤 Chat exported as Markdown")

async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
    ]])
    await update.message.reply_markdown("Choose language / Выбери язык:", reply_markup=kb)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_markdown(
        "**AEGIS Commands**\n\n"
        "/start — intro\n"
        "/upgrade — Pro version\n"
        "/incognito — private mode (no saved history)\n"
        "/normal — exit incognito\n"
        "/summarize — condense chat\n"
        "/export — download chat as file\n"
        "/language — switch EN/RU\n"
        "/help — this message"
    )

# ── Callbacks ────────────────────────────────────────
async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    vote = "up" if query.data == "fb_up" else "down"
    _log_feedback(query.message.chat.id, vote)
    emoji = "👍" if vote == "up" else "👎"
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{emoji} Thanks!", callback_data="fb_done"),
    ]]))

async def handle_language_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = "en" if query.data == "lang_en" else "ru"
    if lang == "en":
        await query.edit_message_text("🇬🇧 Language set to **English**. /help for commands.")
    else:
        await query.edit_message_text("🇷🇺 Язык: **Русский**. /help — список команд.")
    logger.info(f"[chat={query.message.chat.id}] language → {lang}")

# ── Message handler ──────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if not msg or not msg.strip():
        return

    chat_type = update.effective_chat.type

    # Group/supergroup: respond only to @mentions or replies
    if chat_type in (ChatType.GROUP, ChatType.SUPERGROUP):
        is_reply = (
            update.message.reply_to_message
            and update.message.reply_to_message.from_user
            and update.message.reply_to_message.from_user.id == context.bot.id
        )
        if not _is_bot_mentioned(msg, update.message.entities) and not is_reply:
            return
        msg = _strip_mention(msg) or "Hello"

    msg = _sanitize_input(msg.strip())
    if not msg:
        await update.message.reply_markdown("⚠️ Blocked by safety filters.")
        return

    chat_id = update.effective_chat.id
    logger.info(f"[chat={chat_id}] {msg[:100]}")
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    reply = await chat_completion(chat_id, msg)
    await update.message.reply_markdown(reply, reply_markup=_build_feedback_kb())

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")

# ── Main ─────────────────────────────────────────────
def main():
    logger.info(f"Starting AEGIS v3.0 (model={MODEL})")
    global conversations
    conversations = _load_state()
    logger.info(f"Restored {len(conversations)} conversations")

    app = Application.builder().token(TOKEN).build()

    async def _startup(app_inst):
        global BOT_USERNAME
        BOT_USERNAME = (await app_inst.bot.get_me()).username
        logger.info(f"Bot: @{BOT_USERNAME}")

    app.post_init = _startup

    # Commands
    for cmd, handler in [
        ("start", cmd_start), ("upgrade", cmd_upgrade), ("incognito", cmd_incognito),
        ("normal", cmd_normal), ("summarize", cmd_summarize), ("export", cmd_export),
        ("language", cmd_language), ("help", cmd_help),
    ]:
        app.add_handler(CommandHandler(cmd, handler))

    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_feedback, pattern="^fb_"))
    app.add_handler(CallbackQueryHandler(handle_language_cb, pattern="^lang_"))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_message))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP), handle_message,
    ))

    app.add_error_handler(error_handler)
    logger.info("Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
