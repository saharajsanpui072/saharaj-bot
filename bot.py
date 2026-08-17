import os
import threading
import logging
import sqlite3
import asyncio
import requests
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

# ================= DUMMY WEB SERVER (RENDER KEEP-ALIVE) =================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Main Bot & Admin Bot are running live on Render!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# ================= CONFIGURATION =================
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
            balance REAL DEFAULT 0.0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            duration TEXT PRIMARY KEY,
            price REAL
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
    conn.commit()
    conn.close()

def log_transaction(user_id, amount, t_type):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO transactions (user_id, amount, type) VALUES (?, ?, ?)", (user_id, amount, t_type))
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

def get_stats():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(balance) FROM users")
    total_users, total_bal = c.fetchone()
    conn.close()
    return total_users or 0, total_bal or 0.0

# ================= MAIN STORE BOT HANDLERS =================
async def main_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# ================= ADMIN BOT HANDLERS & KEYPAD =================
authenticated_admins = set()
admin_action_state = {}

def generate_keypad(current_amount_str, header_title):
    text = (
        f"╭─────────────────────╮\n"
        f"   💰 **{header_title}**\n"
        f"╰─────────────────────╯\n\n"
        f"💵 **Amount: ₹{current_amount_str or '0'}**\n\n"
        f"Use keypad or type directly in chat.\n"
        f"Min: ₹1.00 | Max: ₹50,000.00"
    )
    keyboard = [
        [InlineKeyboardButton("1", callback_data="num_1"), InlineKeyboardButton("2", callback_data="num_2"), InlineKeyboardButton("3", callback_data="num_3")],
        [InlineKeyboardButton("4", callback_data="num_4"), InlineKeyboardButton("5", callback_data="num_5"), InlineKeyboardButton("6", callback_data="num_6")],
        [InlineKeyboardButton("7", callback_data="num_7"), InlineKeyboardButton("8", callback_data="num_8"), InlineKeyboardButton("9", callback_data="num_9")],
        [InlineKeyboardButton("❌ CLEAR", callback_data="num_clear"), InlineKeyboardButton("0", callback_data="num_0"), InlineKeyboardButton("🔙 BACK", callback_data="num_back")],
        [InlineKeyboardButton("✅ CONFIRM AMOUNT", callback_data="num_confirm")],
        [InlineKeyboardButton("🚪 Return to Main Menu", callback_data="main_menu")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

async def send_admin_menu(chat_id, context: ContextTypes.DEFAULT_TYPE, message_id=None):
    total_users, total_bal = get_stats()
    text = (
        "╔════════════════════════╗\n"
        "   👑 **CENTRAL ADMIN PANEL** 👑\n"
        "╚════════════════════════╝\n\n"
        f"👥 **Total Registered Users:** `{total_users}`\n"
        f"💰 **Total System Balance:** `₹{total_bal:.2f} INR`\n"
        "────────────────────────\n"
        "👇 *Select an action below:*"
    )
    keyboard = [
        [InlineKeyboardButton("👥 Manage Users (Add/Cut)", callback_data="adm_users")],
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
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized access.")
        return
    admin_action_state[user_id] = {"action": "WAIT_PASSCODE", "input_val": ""}
    await update.message.reply_text("🔒 **Enter Admin Passcode:**")

async def handle_admin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    text = update.message.text.strip()
    state = admin_action_state.get(user_id, {})
    current_action = state.get("action")

    if current_action == "WAIT_PASSCODE":
        if text == ADMIN_PASSCODE:
            authenticated_admins.add(user_id)
            admin_action_state[user_id] = {}
            await update.message.reply_text("🔓 **Access Granted! Welcome Admin.**")
            await send_admin_menu(update.effective_chat.id, context)
        else:
            await update.message.reply_text("❌ **Incorrect Passcode!** Try again:")
        return

    if user_id not in authenticated_admins:
        await update.message.reply_text("⚠️ Please send /start and login.")
        return

    if current_action in ["ADD_BAL", "CUT_BAL", "SET_PRICE"]:
        if text.isdigit():
            admin_action_state[user_id]["input_val"] = text
            await execute_admin_action(update, context, is_callback=False)
        else:
            await update.message.reply_text("❌ Please enter numeric values only.")

async def execute_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback=True):
    user_id = update.effective_user.id
    state = admin_action_state.get(user_id, {})
    action = state.get("action")
    input_val = state.get("input_val", "0")

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
        await send_admin_menu(update.callback_query.message.chat_id, context)
    else:
        await update.message.reply_text(res_text, parse_mode="Markdown")
        await send_admin_menu(update.effective_chat.id, context)

async def admin_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in authenticated_admins:
        await query.edit_message_text("⚠️ Session expired. Please send /start to log in.")
        return

    data = query.data
    state = admin_action_state.get(user_id, {})

    if data.startswith("num_"):
        key = data.replace("num_", "")
        current_val = state.get("input_val", "")
        if key.isdigit():
            current_val = key if current_val == "0" else (current_val + key)
        elif key == "clear":
            current_val = ""
        elif key == "back":
            current_val = current_val[:-1]
        elif key == "confirm":
            await execute_admin_action(update, context, is_callback=True)
            return

        admin_action_state[user_id]["input_val"] = current_val
        header = state.get("header", "ENTER CUSTOM AMOUNT")
        text, markup = generate_keypad(current_val, header)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            pass
        return

    if data == "main_menu":
        admin_action_state[user_id] = {}
        await send_admin_menu(query.message.chat_id, context, query.message.message_id)
    elif data == "adm_logout":
        authenticated_admins.discard(user_id)
        admin_action_state[user_id] = {}
        await query.edit_message_text("🔒 Logged out successfully. Send /start to log in again.")
    elif data == "adm_users":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id, full_name, balance FROM users ORDER BY user_id DESC LIMIT 15")
        users = c.fetchall()
        conn.close()
        keyboard = [[InlineKeyboardButton(f"👤 {u[1]} (₹{u[2]:.2f})", callback_data=f"seluser_{u[0]}")] for u in users]
        keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")])
        await query.edit_message_text("👥 **Select User to Manage Balance:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif data.startswith("seluser_"):
        target_id = int(data.split("_")[1])
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT full_name, username, balance FROM users WHERE user_id = ?", (target_id,))
        user_info = c.fetchone()
        conn.close()
        text = f"👤 **User:** {user_info[0]} (@{user_info[1]})\n🆔 **ID:** `{target_id}`\n💰 **Current Balance:** `₹{user_info[2]:.2f}`\n\nChoose action:"
        keyboard = [
            [InlineKeyboardButton("➕ Add Balance", callback_data=f"act_add_{target_id}"), InlineKeyboardButton("➖ Cut Balance", callback_data=f"act_cut_{target_id}")],
            [InlineKeyboardButton("🔙 Back to Users", callback_data="adm_users")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif data.startswith("act_add_"):
        target_id = int(data.split("_")[2])
        header = f"ADD BALANCE (ID: {target_id})"
        admin_action_state[user_id] = {"action": "ADD_BAL", "target_id": target_id, "input_val": "", "header": header}
        text, markup = generate_keypad("", header)
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
    elif data.startswith("act_cut_"):
        target_id = int(data.split("_")[2])
        header = f"DEDUCT BALANCE (ID: {target_id})"
        admin_action_state[user_id] = {"action": "CUT_BAL", "target_id": target_id, "input_val": "", "header": header}
        text, markup = generate_keypad("", header)
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
    elif data == "adm_prices":
        prices = get_prices()
        keyboard = [[InlineKeyboardButton(f"⚡ {d} ➔ ₹{p:.2f}", callback_data=f"selprice_{d}")] for d, p in prices.items()]
        keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")])
        await query.edit_message_text("🏷 **Select Package to Change Price:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif data.startswith("selprice_"):
        duration = data.replace("selprice_", "")
        header = f"SET NEW PRICE ({duration})"
        admin_action_state[user_id] = {"action": "SET_PRICE", "duration": duration, "input_val": "", "header": header}
        text, markup = generate_keypad("", header)
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
    elif data == "adm_history":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT user_id, amount, type, timestamp FROM transactions ORDER BY id DESC LIMIT 10")
        logs = c.fetchall()
        conn.close()
        text = "📜 **Last 10 Transactions History:**\n────────────────────────\n"
        if logs:
            for l in logs:
                action_icon = "➕ ADD" if l[2] == "ADD" else "➖ CUT"
                text += f"{action_icon} | ID: `{l[0]}` | Amount: `₹{l[1]:.2f}`\n⏱ Time: `{l[3]}`\n────────────────────────\n"
        else:
            text += "No transactions recorded yet.\n"
        keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ================= ASYNC RUNNER FOR BOTH BOTS =================
async def run_bots():
    init_db()

    # Main Bot Setup
    main_app = Application.builder().token(MAIN_BOT_TOKEN).build()
    main_app.add_handler(CommandHandler("start", main_start))
    main_app.add_handler(CallbackQueryHandler(main_start, pattern="^refresh_dash$"))
    main_app.add_handler(CallbackQueryHandler(open_store, pattern="^open_store$"))
    main_app.add_handler(CallbackQueryHandler(process_purchase, pattern="^buy_"))

    # Admin Bot Setup
    admin_app = Application.builder().token(ADMIN_BOT_TOKEN).build()
    admin_app.add_handler(CommandHandler("start", admin_start))
    admin_app.add_handler(CallbackQueryHandler(admin_callback_router))
    admin_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_msg))

    await main_app.initialize()
    await admin_app.initialize()
    await main_app.start()
    await admin_app.start()
    
    await main_app.updater.start_polling()
    await admin_app.updater.start_polling()
    
    print("🚀 Both Store Bot and Admin Bot are running concurrently on Render!")
    while True:
        await asyncio.sleep(1000)

def main():
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(run_bots())

if __name__ == "__main__":
    main()
