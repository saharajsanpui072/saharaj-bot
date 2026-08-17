import os
import threading
import logging
import sqlite3
import asyncio
import requests
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ================= DUMMY WEB SERVER FOR RENDER =================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running on Render!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# ================= BOT CONFIGURATION =================
BOT_TOKEN = "8931305926:AAEl-PDRDn7PHfTBDSmTwryZEoTFkdQFgDs"
ADMIN_ID = 6599070855
ADMIN_USERNAME = "saharajsanpui"

API_ENDPOINT = "https://xyzcheats.com/api/reseller_v1.php"
MASTER_KEY = "a7f3e8b2c9d1f4a6b8c2d5e9f1a3b6c8"
API_KEY = "67f6be5953d6648a524fa6c88e5f327c"
PRODUCT_ID = "136"
PRODUCT_DISPLAY_NAME = "SAHARAJ EXE V2"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# ================= DATABASE =================
def get_db():
    conn = sqlite3.connect("store.db", timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            balance REAL DEFAULT 0.0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            duration TEXT PRIMARY KEY,
            price REAL
        )
    """)
    default_plans = [
        ("1 Hours", 25.0),
        ("3 Hours", 50.0),
        ("6 Hours", 80.0),
        ("12 Hours", 150.0),
        ("1 DaYs", 300.0),
        ("2 DaYs", 800.0),
        ("3 DaYs", 950.0),
        ("5 DaYs", 1500.0),
        ("7 DaYs", 1900.0)
    ]
    c.executemany("INSERT OR IGNORE INTO prices (duration, price) VALUES (?, ?)", default_plans)
    conn.commit()
    conn.close()

def get_user(user_id, username, full_name):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (user_id, username, full_name, balance) VALUES (?, ?, ?, ?)",
                  (user_id, username or "N/A", full_name or "N/A", 0.0))
        conn.commit()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = c.fetchone()
    conn.close()
    return user

def get_user_balance(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0.0

def get_prices():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT duration, price FROM prices")
    rows = c.fetchall()
    conn.close()
    return dict(rows)

# ================= BOT UI =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        tg_user = query.from_user
    else:
        tg_user = update.effective_user

    user = get_user(tg_user.id, tg_user.username, tg_user.full_name)
    balance = user[3]

    text = (
        "╔════════════════════════╗\n"
        f"   ⚡ **{PRODUCT_DISPLAY_NAME} STORE** ⚡\n"
        "╚════════════════════════╝\n\n"
        f"👤 **Account Name:** `{tg_user.first_name}`\n"
        f"🆔 **User ID:** `{tg_user.id}`\n"
        f"🌐 **Username:** @{tg_user.username if tg_user.username else 'N/A'}\n"
        "────────────────────────\n"
        f"💰 **Wallet Balance:** `₹{balance:.2f} INR`\n"
        "────────────────────────\n"
        "👇 *Select an option below:*"
    )

    keyboard = [
        [InlineKeyboardButton(f"🛒 Purchase Key ({PRODUCT_DISPLAY_NAME})", callback_data="open_store")],
        [InlineKeyboardButton("💳 Deposit Funds", url=f"https://t.me/{ADMIN_USERNAME}")],
        [InlineKeyboardButton("🔄 Refresh Dashboard", callback_data="refresh_dash")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def open_store(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    current_bal = get_user_balance(user_id)
    prices = get_prices()

    text = (
        "╔════════════════════════╗\n"
        "     📦 **SELECT PACKAGE PLAN** 📦\n"
        "╚════════════════════════╝\n\n"
        f"💳 **Your Current Balance:** `₹{current_bal:.2f} INR`\n"
        f"🏷 **Product:** `{PRODUCT_DISPLAY_NAME}`\n"
        "────────────────────────\n"
        "⚡ *Instant Auto-Delivery via API:*"
    )

    keyboard = []
    for duration, price in prices.items():
        keyboard.append([
            InlineKeyboardButton(f"⚡ {duration} ➔ ₹{price:.2f}", callback_data=f"buy_{duration}")
        ])

    keyboard.append([InlineKeyboardButton("💳 Deposit Funds", url=f"https://t.me/{ADMIN_USERNAME}")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Main Dashboard", callback_data="refresh_dash")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def process_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    duration = query.data.replace("buy_", "").strip()

    prices = get_prices()
    cost = prices.get(duration)

    if cost is None:
        await query.edit_message_text("❌ Selected plan not found.")
        return

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    current_balance = row[0] if row else 0.0

    if current_balance < cost:
        conn.close()
        insufficient_text = (
            "╔════════════════════════╗\n"
            "   ❌ **INSUFFICIENT BALANCE** ❌\n"
            "╚════════════════════════╝\n\n"
            f"⏱ **Selected Plan:** `{duration}`\n"
            f"🏷 **Required Amount:** `₹{cost:.2f}`\n"
            f"💰 **Your Balance:** `₹{current_balance:.2f}`\n"
            "────────────────────────\n"
            "⚠️ *Please deposit funds from Admin to purchase.*"
        )
        keyboard = [
            [InlineKeyboardButton("💳 Contact Admin to Deposit", url=f"https://t.me/{ADMIN_USERNAME}")],
            [InlineKeyboardButton("🔙 Back to Packages", callback_data="open_store")]
        ]
        await query.edit_message_text(insufficient_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    await query.edit_message_text(f"⏳ **Generating `{duration}` Key from API... Please wait...**", parse_mode="Markdown")

    payload = {
        "api_key": API_KEY,
        "action": "buy",
        "product_id": PRODUCT_ID,
        "duration": duration
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "x-master-key": MASTER_KEY
    }

    loop = asyncio.get_running_loop()
    try:
        res = await loop.run_in_executor(None, lambda: requests.post(API_ENDPOINT, data=payload, headers=headers, timeout=25))
        try:
            data = res.json()
        except Exception:
            data = {"status": "failed", "msg": res.text[:120]}

        license_key = None
        if isinstance(data, dict):
            license_key = data.get("key") or data.get("license") or (data.get("data", {}).get("key") if isinstance(data.get("data"), dict) else None)

        if license_key or data.get("status") == "success":
            new_balance = current_balance - cost
            c.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
            conn.commit()
            conn.close()

            final_key = license_key if license_key else "KEY-GENERATED-SUCCESS"
            success_text = (
                "╔════════════════════════╗\n"
                "   🎉 **PURCHASE SUCCESSFUL** 🎉\n"
                "╚════════════════════════╝\n\n"
                f"📦 **Product:** `{PRODUCT_DISPLAY_NAME}`\n"
                f"⏱ **Duration Plan:** `{duration}`\n"
                f"💰 **Deducted:** `₹{cost:.2f}`\n"
                f"💳 **Remaining Balance:** `₹{new_balance:.2f}`\n"
                "────────────────────────\n"
                f"🔑 **YOUR LICENSE KEY:**\n`{final_key}`\n"
                "────────────────────────\n"
                "⚠️ *Tap above key to copy. Only visible to you.*"
            )
            keyboard = [
                [InlineKeyboardButton("🛒 Buy Another Key", callback_data="open_store")],
                [InlineKeyboardButton("🔙 Main Dashboard", callback_data="refresh_dash")]
            ]
            await query.edit_message_text(success_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            conn.close()
            error_msg = data.get("msg") or data.get("message") or "API Order Rejected"
            fail_text = f"❌ **API Error:** `{error_msg}`\n\nNo money was deducted from your wallet."
            keyboard = [[InlineKeyboardButton("🔙 Back to Store", callback_data="open_store")]]
            await query.edit_message_text(fail_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except Exception as e:
        conn.close()
        await query.edit_message_text(f"❌ **Connection Error:** `{str(e)}`")

# ================= MAIN =================
def main():
    init_db()
    
    # Start web server thread for Render
    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(start, pattern="^refresh_dash$"))
    app.add_handler(CallbackQueryHandler(open_store, pattern="^open_store$"))
    app.add_handler(CallbackQueryHandler(process_purchase, pattern="^buy_"))

    print("🤖 Bot is running on Render...")
    app.run_polling()

if __name__ == "__main__":
    main()
  
