#!/usr/bin/env python3
"""
Aegis Stars Payment Handler — long-polling обработчик Telegram Stars платежей.
@miropolbot: /start → invoice, pre_checkout_query → OK, successful_payment → Pro.
"""

import os, json, sqlite3, sys, time
from datetime import datetime, timedelta
from urllib.request import urlopen, Request

BOT_TOKEN = os.environ.get("STARS_BOT_TOKEN", "")
PRO_PRICE_STARS = 100
DB_PATH = os.path.expanduser("~/.hermes/data/stars_payments.db")
POLL_TIMEOUT = 10
ERROR_SLEEP = 5

def tg_api(method, data=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    req = Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"}) if data else Request(url)
    with urlopen(req, timeout=45) as r:
        return json.loads(r.read())

def send_invoice(chat_id):
    return tg_api("sendInvoice", {
        "chat_id": chat_id, "title": "Aegis AI Engine Pro",
        "description": "Pro на 30 дн.\nБезлимит • 154+ скиллов • Трейдинг • Память • Приоритет",
        "payload": "pro_monthly_30days", "currency": "XTR",
        "prices": [{"label": "Pro (30 дней)", "amount": PRO_PRICE_STARS}],
        "provider_token": "", "start_parameter": "pro_upgrade",
    })

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL, telegram_username TEXT, amount_stars INTEGER NOT NULL, telegram_payment_id TEXT UNIQUE, status TEXT DEFAULT 'pending', expires_at TEXT, created_at TEXT DEFAULT (datetime('now','localtime')))")
    c.execute("CREATE TABLE IF NOT EXISTS pro_users (telegram_id INTEGER PRIMARY KEY, telegram_username TEXT, activated_at TEXT, expires_at TEXT NOT NULL, active INTEGER DEFAULT 1)")
    c.commit()
    return c

def save_payment(conn, tg_id, username, amount, payment_id):
    expires = (datetime.now() + timedelta(days=30)).isoformat()
    try:
        conn.execute("INSERT INTO payments (telegram_id, telegram_username, amount_stars, telegram_payment_id, status, expires_at) VALUES (?,?,?,?,?,?)", (tg_id, username, amount, payment_id, 'confirmed', expires))
    except sqlite3.IntegrityError:
        return
    conn.execute("INSERT OR REPLACE INTO pro_users (telegram_id, telegram_username, activated_at, expires_at, active) VALUES (?,?,datetime('now','localtime'),?,1)", (tg_id, username, expires))
    conn.commit()

def process(update, conn, offset):
    uid = update.get("update_id", offset)
    if "message" in update:
        msg = update["message"]; text = msg.get("text",""); user = msg.get("from",{})
        chat_id = msg["chat"]["id"]; tg_id = user.get("id",0); uname = user.get("username", f"user{tg_id}")
        if text == "/start":
            print(f"[START] {uname} ({tg_id})"); r = send_invoice(chat_id)
            print(f"  {'✅' if r.get('ok') else '❌ '+r.get('description','')}")
        elif "successful_payment" in msg:
            sp = msg["successful_payment"]; amt = sp["total_amount"]; pid = sp["telegram_payment_charge_id"]
            print(f"[PAYMENT] {uname} ({tg_id}) — {amt} ⭐"); save_payment(conn, tg_id, uname, amt, pid)
            tg_api("sendMessage", {"chat_id": chat_id, "text": f"✅ *Оплата получена!*\n\nPro на 30 дн.\n{amt} ⭐\n\nПиши /start в @Morearbot 🚀\nДоступ активируется через 1–2 минуты.", "parse_mode": "Markdown"})
    elif "pre_checkout_query" in update:
        pq = update["pre_checkout_query"]; pq_id = pq["id"]; amt = pq["total_amount"]
        user = pq["from"]; tg_id = user["id"]; uname = user.get("username", f"user{tg_id}")
        print(f"[PRE] {uname} ({tg_id}) — {amt} ⭐")
        if amt >= PRO_PRICE_STARS:
            tg_api("answerPreCheckoutQuery", {"pre_checkout_query_id": pq_id, "ok": True}); print("  ✅")
        else:
            tg_api("answerPreCheckoutQuery", {"pre_checkout_query_id": pq_id, "ok": False, "error_message": f"Мин {PRO_PRICE_STARS} ⭐"}); print(f"  ❌")
    return uid + 1

def main():
    if not BOT_TOKEN:
        print("❌ STARS_BOT_TOKEN не задан!"); sys.exit(1)
    print(f"🚀 @Miropolbot Stars (polling) — {PRO_PRICE_STARS} ⭐")
    tg_api("deleteWebhook", {"drop_pending_updates": False})
    conn = init_db(); offset = 0
    while True:
        try:
            r = tg_api("getUpdates", {"offset": offset, "timeout": POLL_TIMEOUT, "allowed_updates": ["message","pre_checkout_query"]})
            if r.get("ok"):
                for u in r["result"]: offset = process(u, conn, offset)
        except Exception as e:
            print(f"⚠️ {e}"); time.sleep(ERROR_SLEEP)

if __name__ == "__main__":
    main()
