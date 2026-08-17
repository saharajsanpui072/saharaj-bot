import os
import time
import threading
import logging
import sqlite3
import requests
import asyncio
import urllib.parse
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# ================= KEEP-ALIVE SERVER =================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Server 24/7 Alive"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

def keep_alive_ping():
    time.sleep(15)
    while True:
        try:
            port = os.environ.get("PORT", "8080")
            requests.get(f"http://127.0.0.1:{port}/", timeout=10)
        except Exception:
            pass
        time.sleep(240)

# ================= CONFIG =================
MAIN_BOT_TOKEN = "8931305926:AAEl-PDRDn7PHfTBDSmTwryZEoTFkdQFgDs"
ADMIN_BOT_TOKEN = "8124760942:AAHwUlH_WupFwJ8sGSTwRimi0J88zN-selQ"

ADMIN_ID = 6599070855
ADMIN_USERNAME = "saharajsanpui"
ADMIN_PASSCODE = "00365"

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
            balance REAL DEFAULT 0.0,
            is_banned INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            duration TEXT PRIMARY KEY,
            price REAL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            val TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            utr TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            type TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
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
    c.execute("INSERT OR IGNORE INTO settings (key, val) VALUES ('maintenance', 'OFF')")
    c.execute("INSERT OR IGNORE INTO settings (key, val) VALUES ('upi_id', 'example@upi')")
    conn.commit()
    conn.close()

def get_setting(key):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT val FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""

def set_setting(key, val):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, val) VALUES (?, ?)", (key, val))
    conn.commit()
    conn.close()

def log_transaction(user_id, amount, t_type):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO transactions (user_id, amount, type) VALUES (?, ?, ?)", (user_id, amount, t_type))
    conn.commit()
    conn.close()

def get_user(user_id, username=None, full_name=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id, username, full_name, balance, is_banned FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    if not user and username is not None:
        c.execute("INSERT INTO users (user_id, username, full_name, balance, is_banned) VALUES (?, ?, ?, ?, ?)",
                  (user_id, username or "N/A", full_name or "N/A", 0.0, 0))
        conn.commit()
        c.execute("SELECT user_id, username, full_name, balance, is_banned FROM users WHERE user_id = ?", (user_id,))
        user = c.fetchone()
    conn.close()
    return user

def get_prices():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT duration, price FROM prices")
    rows = c.fetchall()
    conn.close()
    return dict(rows)

def get_stats():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(balance) FROM users")
    total_users, total_bal = c.fetchone()
    conn.close()
    return total_users or 0, total_bal or 0.0

# ================= GLOBAL STATES =================
user_action_state = {}
admin_action_state = {}
authenticated_admins = set()

# ================= USER BOT UI & LOGIC =================
def generate_user_keypad(amount_str):
    text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💳 **DEPOSIT FUNDS (ADD MONEY)**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💵 **Selected Amount: ₹{amount_str or '0'}**\n\n"
        "Use on-screen buttons or type directly in chat.\n"
        "Min: ₹10.00 | Max: ₹50,000.00"
    )
    keyboard = [
        [InlineKeyboardButton("1", callback_data="uk_1"), InlineKeyboardButton("2", callback_data="uk_2"), InlineKeyboardButton("3", callback_data="uk_3")],
        [InlineKeyboardButton("4", callback_data="uk_4"), InlineKeyboardButton("5", callback_data="uk_5"), InlineKeyboardButton("6", callback_data="uk_6")],
        [InlineKeyboardButton("7", callback_data="uk_7"), InlineKeyboardButton("8", callback_data="uk_8"), InlineKeyboardButton("9", callback_data="uk_9")],
        [InlineKeyboardButton("❌ CLEAR", callback_data="uk_clear"), InlineKeyboardButton("0", callback_data="uk_0"), InlineKeyboardButton("🔙 BACK", callback_data="uk_back")],
        [InlineKeyboardButton("✅ CONFIRM & PAY", callback_data="uk_confirm")],
        [InlineKeyboardButton("🚪 Return to Main Menu", callback_data="main_menu_user")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

def get_main_dashboard(user_id, first_name, username, balance):
    text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ **{PRODUCT_DISPLAY_NAME} STORE** ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 **Name:** `{first_name}`\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"🌐 **Username:** @{username if username else 'N/A'}\n"
        "──────────────────────\n"
        f"💰 **Wallet Balance:** `₹{balance:.2f} INR`\n"
        "──────────────────────\n"
        "👇 *Select an option below:*"
    )
    keyboard = [
        [InlineKeyboardButton(f"🛒 Purchase Key ({PRODUCT_DISPLAY_NAME})", callback_data="open_store")],
        [InlineKeyboardButton("💳 Deposit Funds (Payment)", callback_data="user_deposit_init")],
        [InlineKeyboardButton("🔄 Refresh Dashboard", callback_data="main_menu_user")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

async def user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tg_user = query.from_user if query else update.effective_user
    if query:
        await query.answer()

    user = get_user(tg_user.id, tg_user.username, tg_user.full_name)
    if user and user[4] == 1:
        msg = "⛔ **Account Banned:** You are restricted from using this bot."
        if query:
            await query.edit_message_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text(msg, parse_mode="Markdown")
        return

    if get_setting("maintenance") == "ON" and tg_user.id != ADMIN_ID:
        m_msg = "🛠 **SYSTEM UNDER MAINTENANCE**\n\nPlease check back shortly."
        if query:
            await query.edit_message_text(m_msg, parse_mode="Markdown")
        else:
            await update.message.reply_text(m_msg, parse_mode="Markdown")
        return

    user_action_state[tg_user.id] = {}
    balance = user[3] if user else 0.0
    text, markup = get_main_dashboard(tg_user.id, tg_user.first_name, tg_user.username, balance)

    if query:
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            await query.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")

async def open_store_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    prices = get_prices()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    current_bal = row[0] if row else 0.0

    text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📦 **SELECT PACKAGE PLAN** 📦\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💳 **Your Balance:** `₹{current_bal:.2f} INR`\n"
        f"🏷 **Product:** `{PRODUCT_DISPLAY_NAME}`\n"
        "──────────────────────\n"
        "⚡ *Instant Auto-Delivery via API:*"
    )
    keyboard = []
    for duration, price in prices.items():
        keyboard.append([InlineKeyboardButton(f"⚡ {duration} ➔ ₹{price:.2f}", callback_data=f"buy_{duration}")])
    keyboard.append([InlineKeyboardButton("💳 Deposit Funds", callback_data="user_deposit_init")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Main Dashboard", callback_data="main_menu_user")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def buy_key_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "❌ **INSUFFICIENT BALANCE** ❌\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⏱ **Plan:** `{duration}`\n"
            f"🏷 **Required:** `₹{cost:.2f}`\n"
            f"💰 **Balance:** `₹{current_balance:.2f}`\n"
            "──────────────────────\n"
            "⚠️ *Please deposit funds to continue.*"
        )
        keyboard = [
            [InlineKeyboardButton("💳 Deposit Funds", callback_data="user_deposit_init")],
            [InlineKeyboardButton("🔙 Back to Packages", callback_data="open_store")]
        ]
        await query.edit_message_text(insufficient_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    # 1. HOLD FUNDS
    temp_balance = current_balance - cost
    c.execute("UPDATE users SET balance = ? WHERE user_id = ?", (temp_balance, user_id))
    conn.commit()
    conn.close()

    await query.edit_message_text(f"⏳ **Generating `{duration}` Key from Server... Please wait...**", parse_mode="Markdown")

    # 2. CALL API
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
            data_resp = res.json()
        except Exception:
            data_resp = {"status": "failed", "msg": res.text[:120]}

        license_key = None
        if isinstance(data_resp, dict):
            license_key = data_resp.get("key") or data_resp.get("license") or (data_resp.get("data", {}).get("key") if isinstance(data_resp.get("data"), dict) else None)

        if license_key or data_resp.get("status") == "success":
            final_key = license_key if license_key else "KEY-GENERATED-SUCCESS"
            success_text = (
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🎉 **PURCHASE SUCCESSFUL** 🎉\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📦 **Product:** `{PRODUCT_DISPLAY_NAME}`\n"
                f"⏱ **Plan:** `{duration}`\n"
                f"💰 **Deducted:** `₹{cost:.2f}`\n"
                f"💳 **Remaining Balance:** `₹{temp_balance:.2f}`\n"
                "──────────────────────\n"
                f"🔑 **YOUR LICENSE KEY:**\n`{final_key}`\n"
                "──────────────────────\n"
                "⚠️ *Tap above key to copy. Only visible to you.*"
            )
            keyboard = [
                [InlineKeyboardButton("🛒 Buy Another Key", callback_data="open_store")],
                [InlineKeyboardButton("🔙 Main Dashboard", callback_data="main_menu_user")]
            ]
            await query.edit_message_text(success_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            # AUTO REFUND
            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (cost, user_id))
            conn.commit()
            conn.close()

            raw_err = str(data_resp.get("msg") or data_resp.get("message") or "")
            
            # ইউজারকে জেনেরিক এরর দেখানো
            fail_text = (
                "⚠️ **Server Temporary Busy/Maintenance!**\n\n"
                "We are currently updating our key stocks. Please try again in a few moments.\n\n"
                f"💰 **₹{cost:.2f} refunded back to your wallet.**"
            )
            keyboard = [[InlineKeyboardButton("🔙 Back to Store", callback_data="open_store")]]
            await query.edit_message_text(fail_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

            # এডমিন বটে ডাইরেক্ট অ্যালার্ট নোটিফিকেশন পাঠানো
            try:
                alert_text = (
                    "🚨 **API BALANCE / STOCK ALERT** 🚨\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚠️ **Error Details:** `{raw_err or 'API Delivery Failed'}`\n"
                    f"📦 **Failed Order Plan:** `{duration}`\n"
                    f"👤 **User ID:** `{user_id}`\n"
                    "👉 *Please recharge your API Reseller Panel balance!*"
                )
                requests.post(
                    f"https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": ADMIN_ID,
                        "text": alert_text,
                        "parse_mode": "Markdown"
                    },
                    timeout=5
                )
            except Exception:
                pass

    except Exception as e:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (cost, user_id))
        conn.commit()
        conn.close()
        await query.edit_message_text(f"⚠️ **Connection Timeout!**\n💰 `₹{cost:.2f}` has been refunded to your wallet.\nPlease try again in a minute.")

async def user_proceed_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback=True):
    user_id = update.effective_user.id
    state = user_action_state.get(user_id, {})
    amount_str = state.get("input_val", "0")

    try:
        amount = float(amount_str)
    except ValueError:
        amount = 0.0

    if amount < 10:
        msg = "❌ Minimum deposit amount is ₹10.00"
        if is_callback:
            await update.callback_query.answer(msg, show_alert=True)
        else:
            await update.message.reply_text(msg)
        return

    upi_id = get_setting("upi_id") or "saharaj@upi"
    upi_payload = f"upi://pay?pa={upi_id}&pn=Store&am={amount:.2f}&cu=INR"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_payload)}"

    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO deposits (user_id, amount, utr, status) VALUES (?, ?, 'WAITING', 'PENDING')", (user_id, amount))
    deposit_id = c.lastrowid
    conn.commit()
    conn.close()

    caption = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💳 **PAYMENT QR CODE GENERATED**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💵 **Payable Amount:** `₹{amount:.2f} INR`\n"
        f"🌐 **UPI ID:** `{upi_id}`\n\n"
        "1️⃣ Scan & Pay the exact amount.\n"
        "2️⃣ Copy **12-digit UTR / Ref No**.\n"
        "3️⃣ **Type/Paste the UTR directly in chat.**"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🚫 Cancel Transaction", callback_data=f"user_cancel_dep_{deposit_id}")]])

    if is_callback:
        try:
            await update.callback_query.message.delete()
        except Exception:
            pass
    
    photo_msg = await context.bot.send_photo(chat_id=user_id, photo=qr_url, caption=caption, reply_markup=markup, parse_mode="Markdown")
    user_action_state[user_id] = {"action": "WAIT_UTR", "deposit_id": deposit_id, "amount": amount, "qr_msg_id": photo_msg.message_id}

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if user and user[4] == 1:
        return
    if get_setting("maintenance") == "ON" and user_id != ADMIN_ID:
        return

    text = update.message.text.strip()
    state = user_action_state.get(user_id, {})
    action = state.get("action")

    if action == "USER_INPUT_AMOUNT":
        if text.isdigit():
            user_action_state[user_id]["input_val"] = text
            await user_proceed_payment(update, context, is_callback=False)
        else:
            await update.message.reply_text("❌ Please enter numeric amount only.")
        return

    if action == "WAIT_UTR":
        deposit_id = state.get("deposit_id")
        amount = state.get("amount")
        qr_msg_id = state.get("qr_msg_id")
        utr = text

        # QR মেসেজ অটো ক্লিন
        if qr_msg_id:
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=qr_msg_id)
            except Exception:
                pass

        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE deposits SET utr = ? WHERE id = ?", (utr, deposit_id))
        conn.commit()
        conn.close()

        user_action_state[user_id] = {}

        await update.message.reply_text(
            "⏳ **Payment Submitted Successfully!**\n\n"
            f"💵 Amount: `₹{amount:.2f}`\n"
            f"🔖 UTR: `{utr}`\n"
            f"📌 Status: `PENDING APPROVAL`\n\n"
            "Admin will review and credit your wallet shortly.",
            parse_mode="Markdown"
        )

        try:
            admin_notif_text = (
                "🔔 **NEW DEPOSIT REQUEST**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 User: `{update.effective_user.full_name}` (@{update.effective_user.username})\n"
                f"🆔 User ID: `{user_id}`\n"
                f"💰 Amount: `₹{amount:.2f}`\n"
                f"🔖 UTR / Txn ID: `{utr}`\n"
                f"🆔 Req ID: `#{deposit_id}`"
            )
            admin_inline = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Approve", "callback_data": f"dep_app_{deposit_id}"},
                        {"text": "❌ Reject", "callback_data": f"dep_rej_{deposit_id}"}
                    ]
                ]
            }
            requests.post(
                f"https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": ADMIN_ID,
                    "text": admin_notif_text,
                    "parse_mode": "Markdown",
                    "reply_markup": admin_inline
                },
                timeout=10
            )
        except Exception as e:
            logging.error(f"Failed Admin Notification: {e}")

async def user_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    user = get_user(user_id)
    if user and user[4] == 1:
        await query.edit_message_text("⛔ You are banned.")
        return

    data = query.data
    state = user_action_state.get(user_id, {})

    if data == "main_menu_user":
        await user_start(update, context)
        return

    if data == "user_deposit_init":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, amount FROM deposits WHERE user_id = ? AND status = 'PENDING'", (user_id,))
        pending = c.fetchone()
        conn.close()

        if pending:
            pend_text = (
                "⚠️ **Pending Deposit Found!**\n\n"
                f"You have a pending request of `₹{pending[1]:.2f}` (ID: #{pending[0]}).\n"
                "Wait for admin approval or cancel it to initiate a new deposit."
            )
            pend_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚫 Cancel Pending Request", callback_data=f"user_cancel_dep_{pending[0]}")],
                [InlineKeyboardButton("🔙 Return to Main Menu", callback_data="main_menu_user")]
            ])
            await query.edit_message_text(pend_text, reply_markup=pend_markup, parse_mode="Markdown")
            return

        user_action_state[user_id] = {"action": "USER_INPUT_AMOUNT", "input_val": ""}
        text, markup = generate_user_keypad("")
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("user_cancel_dep_"):
        dep_id = int(data.split("_")[3])
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM deposits WHERE id = ? AND user_id = ?", (dep_id, user_id))
        conn.commit()
        conn.close()
        await query.edit_message_text("✅ Pending deposit cancelled.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Return", callback_data="main_menu_user")]]))
        return

    if data.startswith("uk_"):
        key = data.replace("uk_", "")
        current_val = state.get("input_val", "")

        if key.isdigit():
            current_val = key if current_val == "0" else (current_val + key)
        elif key == "clear":
            current_val = ""
        elif key == "back":
            current_val = current_val[:-1]
        elif key == "confirm":
            await user_proceed_payment(update, context, is_callback=True)
            return

        user_action_state[user_id]["input_val"] = current_val
        text, markup = generate_user_keypad(current_val)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            pass
        return

# ================= ADMIN BOT UI & LOGIC =================
def generate_admin_keypad(current_val, header_title, is_search=False):
    prefix = "Search: " if is_search else "Amount: ₹"
    sub = "Type / Paste in chat or use numeric buttons:" if is_search else "Min: ₹1.00 | Max: ₹50,000.00"
    text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 **{header_title}**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 **{prefix}{current_val or '0'}**\n\n"
        f"{sub}"
    )
    keyboard = [
        [InlineKeyboardButton("1", callback_data="ak_1"), InlineKeyboardButton("2", callback_data="ak_2"), InlineKeyboardButton("3", callback_data="ak_3")],
        [InlineKeyboardButton("4", callback_data="ak_4"), InlineKeyboardButton("5", callback_data="ak_5"), InlineKeyboardButton("6", callback_data="ak_6")],
        [InlineKeyboardButton("7", callback_data="ak_7"), InlineKeyboardButton("8", callback_data="ak_8"), InlineKeyboardButton("9", callback_data="ak_9")],
        [InlineKeyboardButton("❌ CLEAR", callback_data="ak_clear"), InlineKeyboardButton("0", callback_data="ak_0"), InlineKeyboardButton("🔙 BACK", callback_data="ak_back")],
        [InlineKeyboardButton("✅ CONFIRM & PROCEED", callback_data="ak_confirm")],
        [InlineKeyboardButton("🚪 Return to Main Menu", callback_data="admin_main_menu")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

async def show_admin_user_card(user_info, chat_id, context: ContextTypes.DEFAULT_TYPE, message_id=None):
    ban_status = "🔴 BANNED" if user_info[4] == 1 else "🟢 ACTIVE"
    ban_btn_text = "🟢 Unban User" if user_info[4] == 1 else "🔴 Ban User"
    ban_cb_action = f"act_unban_{user_info[0]}" if user_info[4] == 1 else f"act_ban_{user_info[0]}"

    text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👤 **USER MANAGEMENT PROFILE**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 **Name:** {user_info[2]}\n"
        f"🌐 **Username:** @{user_info[1]}\n"
        f"🆔 **User ID:** `{user_info[0]}`\n"
        f"💰 **Balance:** `₹{user_info[3]:.2f} INR`\n"
        f"🛡 **Status:** `{ban_status}`\n"
        "──────────────────────\n"
        "👇 *Select an administrative action:*"
    )
    keyboard = [
        [
            InlineKeyboardButton("➕ Add Balance", callback_data=f"act_add_{user_info[0]}"),
            InlineKeyboardButton("➖ Cut Balance", callback_data=f"act_cut_{user_info[0]}")
        ],
        [
            InlineKeyboardButton(ban_btn_text, callback_data=ban_cb_action),
            InlineKeyboardButton("🔍 Search Another", callback_data="adm_search_user")
        ],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main_menu")]
    ]
    markup = InlineKeyboardMarkup(keyboard)

    if message_id:
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, parse_mode="Markdown")

async def send_admin_panel(chat_id, context: ContextTypes.DEFAULT_TYPE, message_id=None):
    total_users, total_bal = get_stats()
    maint_status = get_setting("maintenance") or "OFF"
    maint_btn_text = "🛠 Maintenance: [ON] (Turn OFF)" if maint_status == "ON" else "✅ Maintenance: [OFF] (Turn ON)"
    current_upi = get_setting("upi_id") or "Not Set"

    text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👑 **CENTRAL ADMIN PANEL** 👑\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 **Total Registered Users:** `{total_users}`\n"
        f"💰 **Total System Balance:** `₹{total_bal:.2f} INR`\n"
        f"🌐 **Current Store UPI:** `{current_upi}`\n"
        f"🚦 **Store Mode:** `{'UNDER MAINTENANCE' if maint_status == 'ON' else 'LIVE & ACTIVE'}`\n"
        "──────────────────────\n"
        "👇 *Select an option below:*"
    )
    keyboard = [
        [InlineKeyboardButton("👥 Manage Users (Search/Add/Cut/Ban)", callback_data="adm_users")],
        [InlineKeyboardButton("💳 Set Store UPI ID", callback_data="adm_set_upi")],
        [InlineKeyboardButton(maint_btn_text, callback_data="adm_toggle_maint")],
        [InlineKeyboardButton("🏷 Change Key Prices", callback_data="adm_prices")],
        [InlineKeyboardButton("📜 View Transaction History", callback_data="adm_history")],
        [InlineKeyboardButton("🔒 Logout Session", callback_data="adm_logout")]
    ]
    markup = InlineKeyboardMarkup(keyboard)

    if message_id:
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, parse_mode="Markdown")

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if int(user_id) != int(ADMIN_ID):
        await update.message.reply_text("⛔ Unauthorized access.")
        return
    admin_action_state[user_id] = {"action": "WAIT_PASSCODE", "input_val": ""}
    await update.message.reply_text("🔒 **Enter Admin Passcode:**")

async def handle_admin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if int(user_id) != int(ADMIN_ID):
        return

    text = update.message.text.strip()
    state = admin_action_state.get(user_id, {})
    current_action = state.get("action")

    if current_action == "WAIT_PASSCODE":
        if text == ADMIN_PASSCODE:
            authenticated_admins.add(user_id)
            admin_action_state[user_id] = {}
            await update.message.reply_text("🔓 **Access Granted! Welcome Admin.**")
            await send_admin_panel(update.effective_chat.id, context)
        else:
            await update.message.reply_text("❌ **Incorrect Passcode!** Try again:")
        return

    if user_id not in authenticated_admins:
        await update.message.reply_text("⚠️ Please send /start and login.")
        return

    if current_action == "SET_UPI":
        set_setting("upi_id", text)
        admin_action_state[user_id] = {}
        await update.message.reply_text(f"✅ **Store UPI ID updated to:** `{text}`", parse_mode="Markdown")
        await send_admin_panel(update.effective_chat.id, context)
        return

    if current_action == "SEARCH_USER":
        query_str = text.replace("@", "").strip()
        conn = get_db()
        c = conn.cursor()
        if query_str.isdigit():
            c.execute("SELECT user_id, username, full_name, balance, is_banned FROM users WHERE user_id = ? OR username LIKE ?", (int(query_str), f"%{query_str}%"))
        else:
            c.execute("SELECT user_id, username, full_name, balance, is_banned FROM users WHERE username LIKE ? OR full_name LIKE ?", (f"%{query_str}%", f"%{query_str}%"))
        user_info = c.fetchone()
        conn.close()

        if user_info:
            admin_action_state[user_id] = {}
            await show_admin_user_card(user_info, update.effective_chat.id, context)
        else:
            await update.message.reply_text(f"❌ No user found matching: `{text}`\nType or paste User ID / Username again:")
        return

    if current_action in ["ADD_BAL", "CUT_BAL", "SET_PRICE"]:
        if text.replace('.', '', 1).isdigit():
            admin_action_state[user_id]["input_val"] = text
            await execute_admin_keypad_action(update, context, is_callback=False)
        else:
            await update.message.reply_text("❌ Please enter numeric values only.")

async def execute_admin_keypad_action(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback=True):
    user_id = update.effective_user.id
    state = admin_action_state.get(user_id, {})
    action = state.get("action")
    input_val = state.get("input_val", "0")

    if action == "SEARCH_USER":
        target_id_str = input_val.strip()
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id, username, full_name, balance, is_banned FROM users WHERE user_id = ?", (target_id_str,))
        user_info = c.fetchone()
        conn.close()

        if user_info:
            admin_action_state[user_id] = {}
            chat_id = update.callback_query.message.chat_id if is_callback else update.effective_chat.id
            msg_id = update.callback_query.message.message_id if is_callback else None
            await show_admin_user_card(user_info, chat_id, context, msg_id)
        else:
            err_msg = f"❌ User ID `{target_id_str}` not found."
            if is_callback:
                await update.callback_query.answer(err_msg, show_alert=True)
            else:
                await update.message.reply_text(err_msg)
        return

    try:
        amount = float(input_val)
    except ValueError:
        amount = 0.0

    if amount <= 0:
        msg = "❌ Amount must be greater than ₹0.00"
        if is_callback:
            await update.callback_query.answer(msg, show_alert=True)
        else:
            await update.message.reply_text(msg)
        return

    conn = get_db()
    c = conn.cursor()

    if action == "ADD_BAL":
        target_id = state.get("target_id")
        c.execute("SELECT balance FROM users WHERE user_id = ?", (target_id,))
        row = c.fetchone()
        if row:
            new_bal = row[0] + amount
            c.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_bal, target_id))
            conn.commit()
            log_transaction(target_id, amount, "ADD")
            res_text = f"✅ **₹{amount:.2f} ADDED** to User ID `{target_id}`!\n💰 New Balance: `₹{new_bal:.2f}`"
            
            try:
                c.execute("SELECT first_name, username FROM users WHERE user_id = ?", (target_id,))
                u_row = c.fetchone()
                d_text, d_markup = get_main_dashboard(target_id, u_row[0] if u_row else "User", u_row[1] if u_row else "N/A", new_bal)
                requests.post(
                    f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": target_id,
                        "text": f"🎉 **Deposit Approved!**\n`₹{amount:.2f}` has been added to your wallet.\n\n" + d_text,
                        "parse_mode": "Markdown",
                        "reply_markup": d_markup.to_dict()
                    },
                    timeout=5
                )
            except Exception:
                pass
        else:
            res_text = "❌ User not found."

    elif action == "CUT_BAL":
        target_id = state.get("target_id")
        c.execute("SELECT balance FROM users WHERE user_id = ?", (target_id,))
        row = c.fetchone()
        if row:
            new_bal = max(0.0, row[0] - amount)
            c.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_bal, target_id))
            conn.commit()
            log_transaction(target_id, amount, "CUT")
            res_text = f"✅ **₹{amount:.2f} DEDUCTED** from User ID `{target_id}`!\n💰 New Balance: `₹{new_bal:.2f}`"
        else:
            res_text = "❌ User not found."

    elif action == "SET_PRICE":
        duration = state.get("duration")
        c.execute("UPDATE prices SET price = ? WHERE duration = ?", (amount, duration))
        conn.commit()
        res_text = f"✅ Price updated for **{duration}** ➔ `₹{amount:.2f}`"

    conn.close()
    admin_action_state[user_id] = {}

    if is_callback:
        await update.callback_query.edit_message_text(res_text, parse_mode="Markdown")
        await send_admin_panel(update.callback_query.message.chat_id, context)
    else:
        await update.message.reply_text(res_text, parse_mode="Markdown")
        await send_admin_panel(update.effective_chat.id, context)

async def admin_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in authenticated_admins:
        await query.edit_message_text("⚠️ Session expired. Send /start to login.")
        return

    data = query.data
    state = admin_action_state.get(user_id, {})

    if data.startswith("ak_"):
        key = data.replace("ak_", "")
        current_val = state.get("input_val", "")

        if key.isdigit():
            current_val = key if current_val == "0" else (current_val + key)
        elif key == "clear":
            current_val = ""
        elif key == "back":
            current_val = current_val[:-1]
        elif key == "confirm":
            await execute_admin_keypad_action(update, context, is_callback=True)
            return

        admin_action_state[user_id]["input_val"] = current_val
        header = state.get("header", "ENTER AMOUNT")
        is_search = (state.get("action") == "SEARCH_USER")
        text, markup = generate_admin_keypad(current_val, header, is_search=is_search)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            pass
        return

    if data.startswith("dep_app_"):
        dep_id = int(data.split("_")[2])
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id, amount, status FROM deposits WHERE id = ?", (dep_id,))
        dep = c.fetchone()
        if dep and dep[2] == "PENDING":
            target_uid, amount = dep[0], dep[1]
            c.execute("UPDATE deposits SET status = 'APPROVED' WHERE id = ?", (dep_id,))
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_uid))
            conn.commit()
            log_transaction(target_uid, amount, "DEPOSIT_APPROVE")

            c.execute("SELECT full_name, username, balance FROM users WHERE user_id = ?", (target_uid,))
            u_data = c.fetchone()
            conn.close()

            await query.edit_message_text(f"✅ **Deposit Approved!** Credited `₹{amount:.2f}` to User ID `{target_uid}`.", parse_mode="Markdown")

            try:
                d_text, d_markup = get_main_dashboard(target_uid, u_data[0] if u_data else "User", u_data[1] if u_data else "N/A", u_data[2] if u_data else amount)
                requests.post(
                    f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": target_uid,
                        "text": f"🎉 **Deposit Approved!**\n`₹{amount:.2f}` has been added to your wallet.\n\n" + d_text,
                        "parse_mode": "Markdown",
                        "reply_markup": d_markup.to_dict()
                    },
                    timeout=5
                )
            except Exception:
                pass
        else:
            conn.close()
            await query.edit_message_text("⚠️ Request was already processed.")
        return

    if data.startswith("dep_rej_"):
        dep_id = int(data.split("_")[2])
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id, amount, status FROM deposits WHERE id = ?", (dep_id,))
        dep = c.fetchone()
        if dep and dep[2] == "PENDING":
            target_uid, amount = dep[0], dep[1]
            c.execute("UPDATE deposits SET status = 'REJECTED' WHERE id = ?", (dep_id,))
            conn.commit()
            conn.close()

            await query.edit_message_text(f"❌ **Deposit Rejected** for User ID `{target_uid}`.", parse_mode="Markdown")
            try:
                requests.post(
                    f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": target_uid,
                        "text": f"❌ **Deposit Rejected!**\nYour deposit request of `₹{amount:.2f}` was rejected by admin.",
                        "parse_mode": "Markdown"
                    },
                    timeout=5
                )
            except Exception:
                pass
        else:
            conn.close()
            await query.edit_message_text("⚠️ Request was already processed.")
        return

    if data == "adm_toggle_maint":
        current_st = get_setting("maintenance")
        new_st = "OFF" if current_st == "ON" else "ON"
        set_setting("maintenance", new_st)
        await send_admin_panel(query.message.chat_id, context, query.message.message_id)
        return

    if data == "adm_set_upi":
        admin_action_state[user_id] = {"action": "SET_UPI"}
        await query.edit_message_text("💳 **Send the new UPI ID in chat:**\n(e.g., `saharaj@oksbi`)")
        return

    if data == "admin_main_menu":
        admin_action_state[user_id] = {}
        await send_admin_panel(query.message.chat_id, context, query.message.message_id)

    elif data == "adm_logout":
        authenticated_admins.discard(user_id)
        admin_action_state[user_id] = {}
        await query.edit_message_text("🔒 Logged out successfully. Send /start to login.")

    elif data == "adm_users":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id, full_name, balance FROM users ORDER BY user_id DESC LIMIT 10")
        users = c.fetchall()
        conn.close()

        keyboard = [[InlineKeyboardButton("🔍 🔎 Search User (ID / Username)", callback_data="adm_search_user")]]
        for u in users:
            keyboard.append([InlineKeyboardButton(f"👤 {u[1]} (₹{u[2]:.2f})", callback_data=f"seluser_{u[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main_menu")])
        await query.edit_message_text("👥 **User Management:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "adm_search_user":
        header = "SEARCH USER (ENTER ID)"
        admin_action_state[user_id] = {"action": "SEARCH_USER", "input_val": "", "header": header}
        text, markup = generate_admin_keypad("", header, is_search=True)
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("seluser_"):
        target_id = int(data.split("_")[1])
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id, username, full_name, balance, is_banned FROM users WHERE user_id = ?", (target_id,))
        user_info = c.fetchone()
        conn.close()
        if user_info:
            await show_admin_user_card(user_info, query.message.chat_id, context, query.message.message_id)
        else:
            await query.edit_message_text("❌ User not found.")

    elif data.startswith("act_ban_"):
        target_id = int(data.split("_")[2])
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        c.execute("SELECT user_id, username, full_name, balance, is_banned FROM users WHERE user_id = ?", (target_id,))
        user_info = c.fetchone()
        conn.close()
        await show_admin_user_card(user_info, query.message.chat_id, context, query.message.message_id)

    elif data.startswith("act_unban_"):
        target_id = int(data.split("_")[2])
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (target_id,))
        conn.commit()
        c.execute("SELECT user_id, username, full_name, balance, is_banned FROM users WHERE user_id = ?", (target_id,))
        user_info = c.fetchone()
        conn.close()
        await show_admin_user_card(user_info, query.message.chat_id, context, query.message.message_id)

    elif data.startswith("act_add_"):
        target_id = int(data.split("_")[2])
        header = f"ADD BALANCE (ID: {target_id})"
        admin_action_state[user_id] = {"action": "ADD_BAL", "target_id": target_id, "input_val": "", "header": header}
        text, markup = generate_admin_keypad("", header)
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("act_cut_"):
        target_id = int(data.split("_")[2])
        header = f"DEDUCT BALANCE (ID: {target_id})"
        admin_action_state[user_id] = {"action": "CUT_BAL", "target_id": target_id, "input_val": "", "header": header}
        text, markup = generate_admin_keypad("", header)
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")

    elif data == "adm_prices":
        prices = get_prices()
        keyboard = [[InlineKeyboardButton(f"⚡ {d} ➔ ₹{p:.2f}", callback_data=f"selprice_{d}")] for d, p in prices.items()]
        keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main_menu")])
        await query.edit_message_text("🏷 **Select Package to Change Price:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("selprice_"):
        duration = data.replace("selprice_", "")
        header = f"SET NEW PRICE ({duration})"
        admin_action_state[user_id] = {"action": "SET_PRICE", "duration": duration, "input_val": "", "header": header}
        text, markup = generate_admin_keypad("", header)
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")

    elif data == "adm_history":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id, amount, type, timestamp FROM transactions ORDER BY id DESC LIMIT 10")
        logs = c.fetchall()
        conn.close()
        text = "📜 **Last 10 Transactions History:**\n──────────────────────\n"
        if logs:
            for l in logs:
                action_icon = "➕ ADD" if "ADD" in l[2] else "➖ CUT"
                text += f"{action_icon} | ID: `{l[0]}` | Amount: `₹{l[1]:.2f}`\n⏱ Time: `{l[3]}`\n──────────────────────\n"
        else:
            text += "No transactions recorded yet.\n"
        keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ================= ASYNC UNIFIED ENGINE =================
async def run_unified_system():
    init_db()

    # User Store Bot Handlers
    main_app = Application.builder().token(MAIN_BOT_TOKEN).build()
    main_app.add_handler(CommandHandler("start", user_start))
    main_app.add_handler(CallbackQueryHandler(open_store_handler, pattern="^open_store$"))
    main_app.add_handler(CallbackQueryHandler(buy_key_handler, pattern="^buy_"))
    main_app.add_handler(CallbackQueryHandler(user_callback_router))
    main_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))

    # Admin Bot Handlers
    admin_app = Application.builder().token(ADMIN_BOT_TOKEN).build()
    admin_app.add_handler(CommandHandler("start", admin_start))
    admin_app.add_handler(CallbackQueryHandler(admin_callback_router))
    admin_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_msg))

    # Initialize & Start Both
    await main_app.initialize()
    await admin_app.initialize()

    await main_app.start()
    await admin_app.start()

    await main_app.updater.start_polling(drop_pending_updates=True)
    await admin_app.updater.start_polling(drop_pending_updates=True)

    print("🚀 All Features Running Flawlessly!")

    while True:
        await asyncio.sleep(1000)

def main():
    threading.Thread(target=run_web, daemon=True).start()
    threading.Thread(target=keep_alive_ping, daemon=True).start()
    asyncio.run(run_unified_system())

if __name__ == "__main__":
    main()
