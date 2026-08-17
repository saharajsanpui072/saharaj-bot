import os
import time
import threading
import logging
import requests
import asyncio
import urllib.parse
from flask import Flask, request, render_template_string, redirect, session
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# ================= CONFIGURATION =================
FIREBASE_URL = "https://saharaj-07-default-rtdb.firebaseio.com"

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

# পারফেক্ট ক্রমানুসারী প্ল্যান লিস্ট
ORDERED_PLANS = [
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

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# ================= FIREBASE DATABASE ENGINE =================
def fb_get(path):
    try:
        r = requests.get(f"{FIREBASE_URL}/{path}.json", timeout=10)
        res = r.json()
        return res if res is not None else {}
    except Exception as e:
        logging.error(f"Firebase GET Error: {e}")
        return {}

def fb_set(path, data):
    try:
        requests.put(f"{FIREBASE_URL}/{path}.json", json=data, timeout=10)
    except Exception as e:
        logging.error(f"Firebase SET Error: {e}")

def fb_update(path, data):
    try:
        requests.patch(f"{FIREBASE_URL}/{path}.json", json=data, timeout=10)
    except Exception as e:
        logging.error(f"Firebase UPDATE Error: {e}")

def init_firebase():
    prices = fb_get("prices")
    if not isinstance(prices, dict) or len(prices) == 0:
        default_dict = {plan: price for plan, price in ORDERED_PLANS}
        fb_set("prices", default_dict)

    settings = fb_get("settings")
    if not isinstance(settings, dict) or not settings:
        fb_set("settings", {"maintenance": "OFF", "upi_id": "saharaj007007@axl"})

def get_user(user_id, username=None, full_name=None):
    user = fb_get(f"users/{user_id}")
    if not isinstance(user, dict) or not user:
        if username is not None:
            user = {
                "user_id": int(user_id),
                "username": username or "N/A",
                "full_name": full_name or "N/A",
                "balance": 0.0,
                "is_banned": 0
            }
            fb_set(f"users/{user_id}", user)
        else:
            return None
    return user

def get_user_balance(user_id):
    user = get_user(user_id)
    if isinstance(user, dict):
        return float(user.get("balance", 0.0))
    return 0.0

def get_prices():
    prices = fb_get("prices")
    res = {}
    if isinstance(prices, dict):
        for k, v in prices.items():
            try:
                res[str(k)] = float(v)
            except Exception:
                pass
    return res

def get_setting(key):
    settings = fb_get("settings")
    if isinstance(settings, dict):
        return settings.get(key, "")
    return ""

def set_setting(key, val):
    fb_update("settings", {key: val})

def log_transaction(user_id, amount, t_type):
    txn = {
        "user_id": int(user_id),
        "amount": float(amount),
        "type": t_type,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        requests.post(f"{FIREBASE_URL}/transactions.json", json=txn, timeout=10)
    except Exception:
        pass

def get_stats():
    users = fb_get("users")
    if not isinstance(users, dict):
        return 0, 0.0
    total_users = len(users)
    total_bal = sum(float(u.get("balance", 0)) for u in users.values() if isinstance(u, dict))
    return total_users, total_bal

# ================= GLOBAL STATES =================
user_action_state = {}
admin_action_state = {}
authenticated_admins = set()

# ================= FLASK WEB SERVER & HTML DASHBOARD =================
web_app = Flask(__name__)
web_app.secret_key = "saharaj_secret_cloud_key_secure"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Saharaj Bot Admin Panel</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #0f172a; color: #f8fafc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; }
        .table { color: #f8fafc; }
        .table-dark { background: #1e293b; }
        .badge-banned { background: #ef4444; }
        .badge-active { background: #22c55e; }
        .btn-custom { background: #6366f1; border: none; }
        .btn-custom:hover { background: #4f46e5; }
    </style>
</head>
<body class="p-3 p-md-5">
<div class="container">
    {% if not session.get('logged_in') %}
    <div class="row justify-content-center mt-5">
        <div class="col-md-4">
            <div class="card p-4 shadow">
                <h4 class="text-center text-primary mb-3">👑 Admin Login</h4>
                {% if error %}<div class="alert alert-danger p-2">{{ error }}</div>{% endif %}
                <form method="POST" action="/admin/login">
                    <div class="mb-3">
                        <label class="form-label">Admin Passcode</label>
                        <input type="password" name="passcode" class="form-control bg-dark text-white border-secondary" required placeholder="Enter passcode">
                    </div>
                    <button type="submit" class="btn btn-custom w-100 py-2 text-white">Login</button>
                </form>
            </div>
        </div>
    </div>
    {% else %}
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h2>⚡ Saharaj Central Cloud Panel</h2>
        <a href="/admin/logout" class="btn btn-outline-danger btn-sm">Logout</a>
    </div>

    <div class="row g-3 mb-4">
        <div class="col-md-3">
            <div class="card p-3">
                <small class="text-secondary">Total Users</small>
                <h3 class="text-info">{{ total_users }}</h3>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card p-3">
                <small class="text-secondary">System Balance</small>
                <h3 class="text-success">₹{{ "%.2f"|format(total_bal) }}</h3>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card p-3">
                <small class="text-secondary">Store UPI ID</small>
                <h5 class="text-warning text-truncate">{{ settings.get('upi_id', 'Not Set') }}</h5>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card p-3">
                <small class="text-secondary">Maintenance Mode</small>
                <h5><span class="badge {{ 'bg-danger' if settings.get('maintenance') == 'ON' else 'bg-success' }}">{{ settings.get('maintenance', 'OFF') }}</span></h5>
            </div>
        </div>
    </div>

    <div class="card p-4 mb-4">
        <h5 class="mb-3">⚙️ Global Settings</h5>
        <form method="POST" action="/admin/settings" class="row g-3">
            <div class="col-md-5">
                <label class="form-label">Store UPI ID</label>
                <input type="text" name="upi_id" class="form-control bg-dark text-white border-secondary" value="{{ settings.get('upi_id', '') }}">
            </div>
            <div class="col-md-4">
                <label class="form-label">Maintenance Mode</label>
                <select name="maintenance" class="form-select bg-dark text-white border-secondary">
                    <option value="OFF" {% if settings.get('maintenance') == 'OFF' %}selected{% endif %}>OFF (Store Live)</option>
                    <option value="ON" {% if settings.get('maintenance') == 'ON' %}selected{% endif %}>ON (Store Locked)</option>
                </select>
            </div>
            <div class="col-md-3 d-flex align-items-end">
                <button type="submit" class="btn btn-custom text-white w-100">Save Settings</button>
            </div>
        </form>
    </div>

    <div class="card p-4">
        <h5 class="mb-3">👥 User Database Management</h5>
        <div class="table-responsive">
            <table class="table table-dark table-hover align-middle">
                <thead>
                    <tr>
                        <th>User ID</th>
                        <th>Name</th>
                        <th>Username</th>
                        <th>Balance</th>
                        <th>Status</th>
                        <th>Quick Modify Balance</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    {% for uid, u in users.items() %}
                    {% if u is mapping %}
                    <tr>
                        <td><code>{{ uid }}</code></td>
                        <td>{{ u.get('full_name', 'N/A') }}</td>
                        <td>@{{ u.get('username', 'N/A') }}</td>
                        <td class="text-success fw-bold">₹{{ "%.2f"|format(u.get('balance', 0)|float) }}</td>
                        <td>
                            {% if u.get('is_banned') == 1 %}
                            <span class="badge badge-banned">Banned</span>
                            {% else %}
                            <span class="badge badge-active">Active</span>
                            {% endif %}
                        </td>
                        <td>
                            <form method="POST" action="/admin/user/balance" class="d-flex gap-2">
                                <input type="hidden" name="user_id" value="{{ uid }}">
                                <input type="number" step="0.01" name="amount" class="form-control form-control-sm bg-dark text-white border-secondary" style="width: 100px;" placeholder="Amount" required>
                                <button type="submit" name="action" value="add" class="btn btn-sm btn-success">+</button>
                                <button type="submit" name="action" value="cut" class="btn btn-sm btn-danger">-</button>
                            </form>
                        </td>
                        <td>
                            <form method="POST" action="/admin/user/ban">
                                <input type="hidden" name="user_id" value="{{ uid }}">
                                {% if u.get('is_banned') == 1 %}
                                <button type="submit" name="status" value="0" class="btn btn-sm btn-outline-success">Unban</button>
                                {% else %}
                                <button type="submit" name="status" value="1" class="btn btn-sm btn-outline-danger">Ban</button>
                                {% endif %}
                            </form>
                        </td>
                    </tr>
                    {% endif %}
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    {% endif %}
</div>
</body>
</html>
"""

@web_app.route('/')
def home():
    return "Firebase Cloud Bot Server is Alive 24/7!"

@web_app.route('/admin')
def admin_page():
    if not session.get('logged_in'):
        return render_template_string(HTML_TEMPLATE)
    users = fb_get("users")
    if not isinstance(users, dict):
        users = {}
    settings = fb_get("settings")
    if not isinstance(settings, dict):
        settings = {}
    total_users, total_bal = get_stats()
    return render_template_string(HTML_TEMPLATE, users=users, settings=settings, total_users=total_users, total_bal=total_bal)

@web_app.route('/admin/login', methods=['POST'])
def admin_login():
    passcode = request.form.get('passcode')
    if passcode == ADMIN_PASSCODE:
        session['logged_in'] = True
        return redirect('/admin')
    return render_template_string(HTML_TEMPLATE, error="Invalid passcode!")

@web_app.route('/admin/logout')
def admin_logout():
    session.pop('logged_in', None)
    return redirect('/admin')

@web_app.route('/admin/settings', methods=['POST'])
def admin_save_settings():
    if not session.get('logged_in'):
        return redirect('/admin')
    upi_id = request.form.get('upi_id')
    maintenance = request.form.get('maintenance')
    fb_update("settings", {"upi_id": upi_id, "maintenance": maintenance})
    return redirect('/admin')

@web_app.route('/admin/user/balance', methods=['POST'])
def admin_mod_balance():
    if not session.get('logged_in'):
        return redirect('/admin')
    user_id = request.form.get('user_id')
    action = request.form.get('action')
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        amount = 0.0

    if amount > 0 and user_id:
        user = get_user(user_id)
        if user and isinstance(user, dict):
            cur_bal = float(user.get("balance", 0.0))
            new_bal = cur_bal + amount if action == "add" else max(0.0, cur_bal - amount)
            fb_update(f"users/{user_id}", {"balance": new_bal})
            log_transaction(int(user_id), amount, "WEB_ADD" if action == "add" else "WEB_CUT")
            
            try:
                msg_text = f"🎉 **Wallet Credited!**\nAdmin added `₹{amount:.2f}` via Web Panel.\n💰 New Balance: `₹{new_bal:.2f}`" if action == "add" else f"⚠️ **Wallet Debited!**\nAdmin deducted `₹{amount:.2f}`.\n💰 Balance: `₹{new_bal:.2f}`"
                requests.post(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage", json={"chat_id": int(user_id), "text": msg_text, "parse_mode": "Markdown"}, timeout=5)
            except Exception:
                pass
    return redirect('/admin')

@web_app.route('/admin/user/ban', methods=['POST'])
def admin_ban_user():
    if not session.get('logged_in'):
        return redirect('/admin')
    user_id = request.form.get('user_id')
    status = int(request.form.get('status', 0))
    if user_id:
        fb_update(f"users/{user_id}", {"is_banned": status})
    return redirect('/admin')

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

# ================= USER BOT UI & LOGIC =================
def generate_user_keypad(amount_str):
    text = (
        "╔════════════════════════╗\n"
        "   💳 **ADD FUNDS / DEPOSIT**\n"
        "╚════════════════════════╝\n\n"
        f"💵 **Selected Amount: ₹{amount_str or '0'}**\n\n"
        "👉 *Use keypad buttons or type directly in chat.*\n"
        "🔹 *Min: ₹10.00 | Max: ₹50,000.00*"
    )
    keyboard = [
        [InlineKeyboardButton("1", callback_data="uk_1"), InlineKeyboardButton("2", callback_data="uk_2"), InlineKeyboardButton("3", callback_data="uk_3")],
        [InlineKeyboardButton("4", callback_data="uk_4"), InlineKeyboardButton("5", callback_data="uk_5"), InlineKeyboardButton("6", callback_data="uk_6")],
        [InlineKeyboardButton("7", callback_data="uk_7"), InlineKeyboardButton("8", callback_data="uk_8"), InlineKeyboardButton("9", callback_data="uk_9")],
        [InlineKeyboardButton("❌ CLEAR", callback_data="uk_clear"), InlineKeyboardButton("0", callback_data="uk_0"), InlineKeyboardButton("🔙 BACK", callback_data="uk_back")],
        [InlineKeyboardButton("✅ CONFIRM & PROCEED TO PAY", callback_data="uk_confirm")],
        [InlineKeyboardButton("🚪 Return to Main Menu", callback_data="main_menu_user")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

def get_main_dashboard(user_id, first_name, username, balance):
    text = (
        "╔════════════════════════╗\n"
        f"   ⚡ **{PRODUCT_DISPLAY_NAME} STORE** ⚡\n"
        "╚════════════════════════╝\n\n"
        f"👤 **Account Name:** `{first_name}`\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"🌐 **Username:** @{username if username else 'N/A'}\n"
        "────────────────────────\n"
        f"💰 **Wallet Balance:** `₹{balance:.2f} INR`\n"
        "────────────────────────\n"
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
    if user and isinstance(user, dict) and user.get("is_banned") == 1:
        msg = "⛔ **Account Restricted:** You have been banned from using this service."
        if query:
            await query.edit_message_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text(msg, parse_mode="Markdown")
        return

    if get_setting("maintenance") == "ON" and tg_user.id != ADMIN_ID:
        m_msg = "🛠 **SYSTEM UNDER MAINTENANCE**\n\nWe are currently upgrading server systems. Please check back shortly!"
        if query:
            await query.edit_message_text(m_msg, parse_mode="Markdown")
        else:
            await update.message.reply_text(m_msg, parse_mode="Markdown")
        return

    user_action_state[tg_user.id] = {}
    balance = float(user.get("balance", 0.0)) if isinstance(user, dict) else 0.0
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
    current_bal = get_user_balance(user_id)

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

    # ফিক্সড অর্ডারে সাজানো বাটন
    for plan_name, default_cost in ORDERED_PLANS:
        price_val = prices.get(plan_name, default_cost)
        keyboard.append([
            InlineKeyboardButton(f"⚡ {plan_name} ➔ ₹{float(price_val):.2f}", callback_data=f"buy_{plan_name}")
        ])

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
        # Fallback to defaults
        for p_name, p_cost in ORDERED_PLANS:
            if p_name == duration:
                cost = p_cost
                break

    if cost is None:
        await query.edit_message_text("❌ Selected plan not found.")
        return

    current_balance = get_user_balance(user_id)

    if current_balance < float(cost):
        insufficient_text = (
            "╔════════════════════════╗\n"
            "   ❌ **INSUFFICIENT BALANCE** ❌\n"
            "╚════════════════════════╝\n\n"
            f"⏱ **Selected Plan:** `{duration}`\n"
            f"🏷 **Required Amount:** `₹{float(cost):.2f}`\n"
            f"💰 **Your Balance:** `₹{current_balance:.2f}`\n"
            "────────────────────────\n"
            "⚠️ *Please deposit funds from below to purchase.*"
        )
        keyboard = [
            [InlineKeyboardButton("💳 Deposit Funds", callback_data="user_deposit_init")],
            [InlineKeyboardButton("🔙 Back to Packages", callback_data="open_store")]
        ]
        await query.edit_message_text(insufficient_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    # 1. HOLD FUNDS
    temp_balance = current_balance - float(cost)
    fb_update(f"users/{user_id}", {"balance": temp_balance})

    await query.edit_message_text(f"⏳ **Generating `{duration}` Key from Server... Please wait...**", parse_mode="Markdown")

    # 2. CALL API DIRECT
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
            log_transaction(user_id, float(cost), f"BUY_{duration}")
            success_text = (
                "╔════════════════════════╗\n"
                "   🎉 **PURCHASE SUCCESSFUL** 🎉\n"
                "╚════════════════════════╝\n\n"
                f"📦 **Product:** `{PRODUCT_DISPLAY_NAME}`\n"
                f"⏱ **Plan:** `{duration}`\n"
                f"💰 **Deducted:** `₹{float(cost):.2f}`\n"
                f"💳 **Remaining Balance:** `₹{temp_balance:.2f}`\n"
                "────────────────────────\n"
                f"🔑 **YOUR LICENSE KEY:**\n`{final_key}`\n"
                "────────────────────────\n"
                "⚠️ *Tap above key to copy. Only visible to you.*"
            )
            keyboard = [
                [InlineKeyboardButton("🛒 Buy Another Key", callback_data="open_store")],
                [InlineKeyboardButton("🔙 Main Dashboard", callback_data="main_menu_user")]
            ]
            await query.edit_message_text(success_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            # AUTO REFUND
            fb_update(f"users/{user_id}", {"balance": current_balance})
            raw_err = str(data_resp.get("msg") or data_resp.get("message") or "")
            
            fail_text = (
                "⚠️ **Server Temporary Busy/Maintenance!**\n\n"
                "We are currently updating our key stocks. Please try again in a few moments.\n\n"
                f"💰 **₹{float(cost):.2f} refunded back to your wallet.**"
            )
            keyboard = [[InlineKeyboardButton("🔙 Back to Store", callback_data="open_store")]]
            await query.edit_message_text(fail_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

            # Admin Alert
            try:
                alert_text = (
                    "🚨 **API BALANCE / STOCK ALERT** 🚨\n"
                    "────────────────────────\n"
                    f"⚠️ **Details:** `{raw_err or 'API Delivery Failed'}`\n"
                    f"📦 **Plan:** `{duration}`\n"
                    f"👤 **User ID:** `{user_id}`\n"
                    "👉 *Please recharge your API reseller panel balance!*"
                )
                requests.post(f"https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/sendMessage", json={"chat_id": ADMIN_ID, "text": alert_text, "parse_mode": "Markdown"}, timeout=5)
            except Exception:
                pass

    except Exception:
        fb_update(f"users/{user_id}", {"balance": current_balance})
        await query.edit_message_text(f"⚠️ **Connection Timeout!**\n💰 `₹{float(cost):.2f}` refunded to your wallet.\nPlease try again.")

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

    upi_id = get_setting("upi_id") or "saharaj007007@axl"
    upi_payload = f"upi://pay?pa={upi_id}&pn=Store&am={amount:.2f}&cu=INR"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_payload)}"

    deposit_id = str(int(time.time()))
    fb_set(f"deposits/{deposit_id}", {
        "id": deposit_id,
        "user_id": int(user_id),
        "amount": float(amount),
        "utr": "WAITING",
        "status": "PENDING"
    })

    caption = (
        "╔════════════════════════╗\n"
        "   💳 **PAYMENT QR CODE**\n"
        "╚════════════════════════╝\n\n"
        f"💵 **Payable Amount:** `₹{amount:.2f} INR`\n"
        f"🌐 **UPI ID:** `{upi_id}`\n\n"
        "1️⃣ Scan & Pay the exact amount.\n"
        "2️⃣ Copy **12-digit UTR / Ref No** after paying.\n"
        "3️⃣ **Type & Send the UTR directly in chat.**"
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
    if user and isinstance(user, dict) and user.get("is_banned") == 1:
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

        if qr_msg_id:
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=qr_msg_id)
            except Exception:
                pass

        fb_update(f"deposits/{deposit_id}", {"utr": utr})
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
                "────────────────────────\n"
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
    if user and isinstance(user, dict) and user.get("is_banned") == 1:
        await query.edit_message_text("⛔ You are banned.")
        return

    data = query.data
    state = user_action_state.get(user_id, {})

    if data == "main_menu_user":
        await user_start(update, context)
        return

    if data == "user_deposit_init":
        deposits = fb_get("deposits")
        pending = None
        if isinstance(deposits, dict):
            for d in deposits.values():
                if isinstance(d, dict) and d.get("user_id") == user_id and d.get("status") == "PENDING":
                    pending = d
                    break

        if pending:
            pend_text = (
                "⚠️ **Pending Deposit Found!**\n\n"
                f"You have a pending request of `₹{pending.get('amount', 0):.2f}` (ID: #{pending.get('id')}).\n"
                "Wait for admin approval or cancel it to initiate a new deposit."
            )
            pend_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚫 Cancel Pending Request", callback_data=f"user_cancel_dep_{pending.get('id')}")],
                [InlineKeyboardButton("🔙 Return to Main Menu", callback_data="main_menu_user")]
            ])
            await query.edit_message_text(pend_text, reply_markup=pend_markup, parse_mode="Markdown")
            return

        user_action_state[user_id] = {"action": "USER_INPUT_AMOUNT", "input_val": ""}
        text, markup = generate_user_keypad("")
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
        return

    if data.startswith("user_cancel_dep_"):
        dep_id = data.split("_")[3]
        requests.delete(f"{FIREBASE_URL}/deposits/{dep_id}.json", timeout=10)
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
        "╔════════════════════════╗\n"
        f"   👑 **{header_title}**\n"
        "╚════════════════════════╝\n\n"
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

def get_admin_panel_content():
    total_users, total_bal = get_stats()
    maint_status = get_setting("maintenance") or "OFF"
    maint_btn_text = "🛠 Maintenance: [ON] (Turn OFF)" if maint_status == "ON" else "✅ Maintenance: [OFF] (Turn ON)"
    current_upi = get_setting("upi_id") or "Not Set"

    text = (
        "╔════════════════════════╗\n"
        "   👑 **CENTRAL ADMIN PANEL** 👑\n"
        "╚════════════════════════╝\n\n"
        f"👥 **Total Registered Users:** `{total_users}`\n"
        f"💰 **Total System Balance:** `₹{total_bal:.2f} INR`\n"
        f"🌐 **Current Store UPI:** `{current_upi}`\n"
        f"🚦 **Store Mode:** `{'UNDER MAINTENANCE' if maint_status == 'ON' else 'LIVE & ACTIVE'}`\n"
        "────────────────────────\n"
        "👇 *Select an option below:*"
    )
    keyboard = [
        [InlineKeyboardButton("👥 Manage Users (Search/Add/Cut/Ban)", callback_data="adm_users")],
        [InlineKeyboardButton("💳 Set Store UPI ID", callback_data="adm_set_upi")],
        [InlineKeyboardButton(maint_btn_text, callback_data="adm_toggle_maint")],
        [InlineKeyboardButton("🏷 Change Key Prices", callback_data="adm_prices")],
        [InlineKeyboardButton("🔒 Logout Session", callback_data="adm_logout")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

async def show_admin_user_card(user_info, chat_id, context: ContextTypes.DEFAULT_TYPE, message_id=None):
    ban_status = "🔴 BANNED" if user_info.get("is_banned") == 1 else "🟢 ACTIVE"
    ban_btn_text = "🟢 Unban User" if user_info.get("is_banned") == 1 else "🔴 Ban User"
    ban_cb_action = f"act_unban_{user_info.get('user_id')}" if user_info.get("is_banned") == 1 else f"act_ban_{user_info.get('user_id')}"

    text = (
        "╔════════════════════════╗\n"
        "   👤 **USER PROFILE CARD**\n"
        "╚════════════════════════╝\n\n"
        f"👤 **Name:** {user_info.get('full_name')}\n"
        f"🌐 **Username:** @{user_info.get('username')}\n"
        f"🆔 **User ID:** `{user_info.get('user_id')}`\n"
        f"💰 **Balance:** `₹{float(user_info.get('balance', 0.0)):.2f} INR`\n"
        f"🛡 **Status:** `{ban_status}`\n"
        "────────────────────────\n"
        "👇 *Select an administrative action:*"
    )
    keyboard = [
        [
            InlineKeyboardButton("➕ Add Balance", callback_data=f"act_add_{user_info.get('user_id')}"),
            InlineKeyboardButton("➖ Cut Balance", callback_data=f"act_cut_{user_info.get('user_id')}")
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
            panel_text, panel_markup = get_admin_panel_content()
            await update.message.reply_text("🔓 **Access Granted! Welcome Admin.**\n\n" + panel_text, reply_markup=panel_markup, parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ **Incorrect Passcode!** Try again:")
        return

    if user_id not in authenticated_admins:
        await update.message.reply_text("⚠️ Please send /start and login.")
        return

    if current_action == "SET_UPI":
        set_setting("upi_id", text)
        admin_action_state[user_id] = {}
        panel_text, panel_markup = get_admin_panel_content()
        await update.message.reply_text(f"✅ **Store UPI ID updated to:** `{text}`\n\n" + panel_text, reply_markup=panel_markup, parse_mode="Markdown")
        return

    if current_action == "SEARCH_USER":
        query_str = text.replace("@", "").strip().lower()
        users = fb_get("users")
        user_info = None
        if isinstance(users, dict):
            for u in users.values():
                if isinstance(u, dict) and (str(u.get("user_id")) == query_str or query_str in str(u.get("username", "")).lower() or query_str in str(u.get("full_name", "")).lower()):
                    user_info = u
                    break

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
        user_info = get_user(target_id_str)

        if user_info and isinstance(user_info, dict):
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

    panel_text, panel_markup = get_admin_panel_content()

    if action == "ADD_BAL":
        target_id = state.get("target_id")
        user = get_user(target_id)
        if user and isinstance(user, dict):
            new_bal = float(user.get("balance", 0.0)) + amount
            fb_update(f"users/{target_id}", {"balance": new_bal})
            log_transaction(target_id, amount, "ADD")
            res_text = f"✅ **₹{amount:.2f} ADDED** to User ID `{target_id}`!\n💰 New Balance: `₹{new_bal:.2f}`"
            
            try:
                d_text, d_markup = get_main_dashboard(target_id, user.get("full_name", "User"), user.get("username", "N/A"), new_bal)
                requests.post(
                    f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": int(target_id),
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
        user = get_user(target_id)
        if user and isinstance(user, dict):
            new_bal = max(0.0, float(user.get("balance", 0.0)) - amount)
            fb_update(f"users/{target_id}", {"balance": new_bal})
            log_transaction(target_id, amount, "CUT")
            res_text = f"✅ **₹{amount:.2f} DEDUCTED** from User ID `{target_id}`!\n💰 New Balance: `₹{new_bal:.2f}`"
        else:
            res_text = "❌ User not found."

    elif action == "SET_PRICE":
        duration = state.get("duration")
        fb_update("prices", {duration: amount})
        res_text = f"✅ Price updated for **{duration}** ➔ `₹{amount:.2f}`"

    admin_action_state[user_id] = {}

    if is_callback:
        await update.callback_query.edit_message_text(res_text + "\n\n" + panel_text, reply_markup=panel_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(res_text + "\n\n" + panel_text, reply_markup=panel_markup, parse_mode="Markdown")

async def admin_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in authenticated_admins:
        await query.edit_message_text("⚠️ Session expired. Send /start to login.")
        return

    data = query.data
    state = admin_action_state.get(user_id, {})
    panel_text, panel_markup = get_admin_panel_content()

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
        dep_id = data.split("_")[2]
        dep = fb_get(f"deposits/{dep_id}")
        if dep and isinstance(dep, dict) and dep.get("status") == "PENDING":
            target_uid, amount = dep.get("user_id"), float(dep.get("amount", 0.0))
            fb_update(f"deposits/{dep_id}", {"status": "APPROVED"})
            
            user = get_user(target_uid)
            cur_bal = float(user.get("balance", 0.0)) if isinstance(user, dict) else 0.0
            new_bal = cur_bal + amount
            fb_update(f"users/{target_uid}", {"balance": new_bal})
            log_transaction(target_uid, amount, "DEPOSIT_APPROVE")

            await query.edit_message_text(f"✅ **Deposit Approved!** Credited `₹{amount:.2f}` to User ID `{target_uid}`.", parse_mode="Markdown")

            try:
                d_text, d_markup = get_main_dashboard(target_uid, user.get("full_name", "User"), user.get("username", "N/A"), new_bal)
                requests.post(
                    f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": int(target_uid),
                        "text": f"🎉 **Deposit Approved!**\n`₹{amount:.2f}` has been added to your wallet.\n\n" + d_text,
                        "parse_mode": "Markdown",
                        "reply_markup": d_markup.to_dict()
                    },
                    timeout=5
                )
            except Exception:
                pass
        else:
            await query.edit_message_text("⚠️ Request was already processed.")
        return

    if data.startswith("dep_rej_"):
        dep_id = data.split("_")[2]
        dep = fb_get(f"deposits/{dep_id}")
        if dep and isinstance(dep, dict) and dep.get("status") == "PENDING":
            target_uid, amount = dep.get("user_id"), float(dep.get("amount", 0.0))
            fb_update(f"deposits/{dep_id}", {"status": "REJECTED"})

            await query.edit_message_text(f"❌ **Deposit Rejected** for User ID `{target_uid}`.", parse_mode="Markdown")
            try:
                requests.post(
                    f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": int(target_uid),
                        "text": f"❌ **Deposit Rejected!**\nYour deposit request of `₹{amount:.2f}` was rejected by admin.",
                        "parse_mode": "Markdown"
                    },
                    timeout=5
                )
            except Exception:
                pass
        else:
            await query.edit_message_text("⚠️ Request was already processed.")
        return

    if data == "adm_toggle_maint":
        current_st = get_setting("maintenance")
        new_st = "OFF" if current_st == "ON" else "ON"
        set_setting("maintenance", new_st)
        p_text, p_markup = get_admin_panel_content()
        await query.edit_message_text(p_text, reply_markup=p_markup, parse_mode="Markdown")
        return

    if data == "adm_set_upi":
        admin_action_state[user_id] = {"action": "SET_UPI"}
        await query.edit_message_text("💳 **Send the new UPI ID in chat:**\n(e.g., `saharaj007007@axl`)")
        return

    if data == "admin_main_menu":
        admin_action_state[user_id] = {}
        await query.edit_message_text(panel_text, reply_markup=panel_markup, parse_mode="Markdown")

    elif data == "adm_logout":
        authenticated_admins.discard(user_id)
        admin_action_state[user_id] = {}
        await query.edit_message_text("🔒 Logged out successfully. Send /start to login.")

    elif data == "adm_users":
        users = fb_get("users")
        keyboard = [[InlineKeyboardButton("🔍 🔎 Search User (ID / Username)", callback_data="adm_search_user")]]
        if isinstance(users, dict):
            for uid, u in list(users.items())[:10]:
                if isinstance(u, dict):
                    keyboard.append([InlineKeyboardButton(f"👤 {u.get('full_name')} (₹{float(u.get('balance', 0)):.2f})", callback_data=f"seluser_{uid}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main_menu")])
        await query.edit_message_text("👥 **User Management (Firebase Cloud):**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "adm_search_user":
        header = "SEARCH USER (ENTER ID)"
        admin_action_state[user_id] = {"action": "SEARCH_USER", "input_val": "", "header": header}
        text, markup = generate_admin_keypad("", header, is_search=True)
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("seluser_"):
        target_id = data.split("_")[1]
        user_info = get_user(target_id)
        if user_info and isinstance(user_info, dict):
            await show_admin_user_card(user_info, query.message.chat_id, context, query.message.message_id)
        else:
            await query.edit_message_text("❌ User not found.")

    elif data.startswith("act_ban_"):
        target_id = data.split("_")[2]
        fb_update(f"users/{target_id}", {"is_banned": 1})
        user_info = get_user(target_id)
        await show_admin_user_card(user_info, query.message.chat_id, context, query.message.message_id)

    elif data.startswith("act_unban_"):
        target_id = data.split("_")[2]
        fb_update(f"users/{target_id}", {"is_banned": 0})
        user_info = get_user(target_id)
        await show_admin_user_card(user_info, query.message.chat_id, context, query.message.message_id)

    elif data.startswith("act_add_"):
        target_id = data.split("_")[2]
        header = f"ADD BALANCE (ID: {target_id})"
        admin_action_state[user_id] = {"action": "ADD_BAL", "target_id": target_id, "input_val": "", "header": header}
        text, markup = generate_admin_keypad("", header)
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("act_cut_"):
        target_id = data.split("_")[2]
        header = f"DEDUCT BALANCE (ID: {target_id})"
        admin_action_state[user_id] = {"action": "CUT_BAL", "target_id": target_id, "input_val": "", "header": header}
        text, markup = generate_admin_keypad("", header)
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")

    elif data == "adm_prices":
        prices = get_prices()
        keyboard = []
        for d, default_p in ORDERED_PLANS:
            p_val = prices.get(d, default_p)
            keyboard.append([InlineKeyboardButton(f"⚡ {d} ➔ ₹{float(p_val):.2f}", callback_data=f"selprice_{d}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main_menu")])
        await query.edit_message_text("🏷 **Select Package to Change Price:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("selprice_"):
        duration = data.replace("selprice_", "")
        header = f"SET NEW PRICE ({duration})"
        admin_action_state[user_id] = {"action": "SET_PRICE", "duration": duration, "input_val": "", "header": header}
        text, markup = generate_admin_keypad("", header)
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")

# ================= ASYNC UNIFIED ENGINE =================
async def run_unified_system():
    init_firebase()

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

    print("🚀 All Plans Ordered Perfectly (1h -> 7d) & Live on Firebase!")

    while True:
        await asyncio.sleep(1000)

def main():
    threading.Thread(target=run_web, daemon=True).start()
    threading.Thread(target=keep_alive_ping, daemon=True).start()
    asyncio.run(run_unified_system())

if __name__ == "__main__":
    main()
