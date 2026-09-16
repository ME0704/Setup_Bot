import os
import json
import time
import secrets
from datetime import datetime, timedelta
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import config

# ROBUST TOKEN RESOLUTION:
TOKEN = (
    getattr(config, "TELEGRAM_BOT_TOKEN", None)
    or os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv(getattr(config, "TELEGRAM_TOKEN_ENV", ""), "")
)

if not TOKEN:
    raise ValueError(
        "Telegram Bot Token not found! Ensure TELEGRAM_BOT_TOKEN is set in your .env file."
    )

bot = telebot.TeleBot(TOKEN)

# Dynamic symbol resolution (supports PAIRS or SYMBOLS)
FOREX_PAIRS = getattr(config, "PAIRS", getattr(config, "SYMBOLS", []))

# Temporary in-memory draft selections
user_drafts = {}
failed_attempts = {}  # { chat_id: {"attempts": int, "lockout_until": datetime} }

# --- DATABASE HELPERS ---
def load_json(filepath: str) -> dict:
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_json(filepath: str, data: dict):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

def check_access(chat_id: str) -> bool:
    if str(chat_id) == str(config.ADMIN_CHAT_ID):
        return True
    users = load_json(config.USERS_DB)
    if str(chat_id) not in users:
        return False
    expiry_str = users[str(chat_id)].get("expiry")
    if not expiry_str:
        return False
    return datetime.now() < datetime.fromisoformat(expiry_str)

def get_expiry_str(chat_id: str) -> str:
    if str(chat_id) == str(config.ADMIN_CHAT_ID):
        return "Lifetime (Admin Access)"
    users = load_json(config.USERS_DB)
    if str(chat_id) in users and users[str(chat_id)].get("expiry"):
        expiry = datetime.fromisoformat(users[str(chat_id)]["expiry"])
        if datetime.now() < expiry:
            return expiry.strftime("%Y-%m-%d %H:%M EAT")
    return "No active subscription"

# --- KEYBOARD BUILDERS ---
def build_main_dashboard(has_access: bool) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    if has_access:
        markup.row(
            InlineKeyboardButton("Configure Pairs", callback_data="nav_pairs"),
            InlineKeyboardButton("My Account", callback_data="nav_account")
        )
    else:
        markup.row(
            InlineKeyboardButton("Plans & Pricing", callback_data="nav_plans"),
            InlineKeyboardButton("Payment Methods", callback_data="nav_payment_methods")
        )
        markup.row(
            InlineKeyboardButton("Enter License Key", callback_data="nav_enter_key"),
            InlineKeyboardButton("My Status", callback_data="nav_account")
        )
        markup.add(
            InlineKeyboardButton("Contact Admin / Submit Receipt", url="https://t.me/emmas_wrld")
        )
    return markup

def build_pairs_keyboard(chat_id: str) -> InlineKeyboardMarkup:
    selected_set = user_drafts.get(chat_id, set())
    markup = InlineKeyboardMarkup()
    
    # 2-column layout tailored for Forex currency pairs
    for i in range(0, len(FOREX_PAIRS), 2):
        row = []
        for j in range(2):
            if i + j < len(FOREX_PAIRS):
                pair = FOREX_PAIRS[i + j]
                icon = "✓" if pair in selected_set else "✕"
                row.append(InlineKeyboardButton(text=f"{icon}  {pair}", callback_data=f"tog_{i+j}"))
        markup.row(*row)

    markup.row(
        InlineKeyboardButton("Select All", callback_data="act_select_all"),
        InlineKeyboardButton("Clear All", callback_data="act_clear_all")
    )
    markup.add(InlineKeyboardButton("Save Selection", callback_data="act_save"))
    markup.add(InlineKeyboardButton("Back to Dashboard", callback_data="nav_home"))
    return markup

# --- ADMIN COMMAND: 16-CHAR BOUND KEY GENERATOR ---
@bot.message_handler(commands=['genkey'])
def generate_key(message):
    chat_id = str(message.chat.id)
    if chat_id != str(config.ADMIN_CHAT_ID):
        return

    # Syntax:
    # /genkey 30              -> Open key for 30 days
    # /genkey 30 @username    -> Bound strictly to that Telegram username
    # /genkey 30 123456789    -> Bound strictly to that numeric Telegram ID
    parts = message.text.split()
    days = 30
    assigned_target = None

    if len(parts) >= 2:
        try:
            days = int(parts[1])
        except ValueError:
            bot.reply_to(
                message,
                "Usage: `/genkey <days> [@username or chat_id]`\nExample: `/genkey 30 @trader_dan`",
                parse_mode="Markdown"
            )
            return

    if len(parts) >= 3:
        assigned_target = parts[2].replace("@", "").strip().lower()

    # Generate 16-character segmented enterprise code: MSR-XXXX-XXXX-XXXX
    raw = secrets.token_hex(6).upper()
    new_key = f"MSR-{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"

    keys_db = load_json(config.KEYS_DB)
    keys_db[new_key] = {
        "days": days,
        "assigned_to": assigned_target,  # None, lowercase username, or chat_id
        "used": False,
        "used_by": None,
        "created_at": datetime.now().isoformat()
    }
    save_json(config.KEYS_DB, keys_db)

    target_text = f"Bound to: `@{assigned_target}`" if assigned_target else "Status: `Unbound (Any account can activate)`"

    bot.reply_to(
        message,
        f"*MS RADAR LICENSE KEY GENERATED*\n\n"
        f"Key: `{new_key}`\n"
        f"Duration: `{days} Days`\n"
        f"{target_text}\n\n"
        f"Send this exact code to the client.",
        parse_mode="Markdown"
    )

# --- USER ACTIVATION (IDENTITY VALIDATION & ANTI-BRUTE-FORCE) ---
@bot.message_handler(commands=['activate'])
def activate_command(message):
    chat_id = str(message.chat.id)
    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(chat_id, "Usage: `/activate MSR-XXXX-XXXX-XXXX`", parse_mode="Markdown")
        return
    process_secure_activation(message, parts[1].strip().upper())

def process_secure_activation(message, entered_key: str):
    chat_id = str(message.chat.id)
    username = (message.from_user.username or "").strip().lower()
    now = datetime.now()

    # 1. Anti-Brute-Force Rate Limiting
    if chat_id in failed_attempts:
        lockout = failed_attempts[chat_id].get("lockout_until")
        if lockout and now < lockout:
            wait_min = int((lockout - now).total_seconds() / 60) + 1
            bot.send_message(
                chat_id,
                f"Account temporarily locked due to repeated failed attempts. Please retry in {wait_min} minutes."
            )
            return

    keys_db = load_json(config.KEYS_DB)

    # 2. Key Existence Check
    if entered_key not in keys_db:
        record_failed_attempt(chat_id)
        bot.send_message(chat_id, "Invalid activation key. Please verify the code and try again.")
        return

    key_record = keys_db[entered_key]

    # 3. Double-Spend Verification
    if key_record["used"]:
        bot.send_message(chat_id, "This license key has already been redeemed.")
        return

    # 4. Identity Binding Verification
    bound_target = key_record.get("assigned_to")
    if bound_target:
        # Check against both Telegram username and numeric chat_id
        if bound_target != username and bound_target != chat_id:
            bot.send_message(
                chat_id,
                "Unauthorized: This license key is cryptographically assigned to another Telegram account."
            )
            return

    # Reset failed counter upon successful validation
    if chat_id in failed_attempts:
        del failed_attempts[chat_id]

    # 5. Apply Subscription
    days_to_add = key_record["days"]
    users = load_json(config.USERS_DB)
    current_expiry = now

    if chat_id in users and users[chat_id].get("expiry"):
        try:
            old_expiry = datetime.fromisoformat(users[chat_id]["expiry"])
            if old_expiry > current_expiry:
                current_expiry = old_expiry
        except Exception:
            pass

    new_expiry = current_expiry + timedelta(days=days_to_add)
    users[chat_id] = {
        "expiry": new_expiry.isoformat(),
        "username": username or None,
        "activated_at": now.isoformat()
    }
    save_json(config.USERS_DB, users)

    # Mark key as consumed
    key_record["used"] = True
    key_record["used_by"] = chat_id
    key_record["redeemed_by_username"] = username or None
    key_record["redeemed_at"] = now.isoformat()
    save_json(config.KEYS_DB, keys_db)

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Configure Pairs", callback_data="nav_pairs"))
    bot.send_message(
        chat_id,
        f"✅ *MS RADAR ACCESS GRANTED*\n\n"
        f"• Duration: `{days_to_add} Days`\n"
        f"• Valid Until: `{new_expiry.strftime('%Y-%m-%d %H:%M EAT')}`\n\n"
        f"Tap below to select your active Forex pairs.",
        reply_markup=markup,
        parse_mode="Markdown"
    )

def record_failed_attempt(chat_id: str):
    now = datetime.now()
    if chat_id not in failed_attempts:
        failed_attempts[chat_id] = {"attempts": 1, "lockout_until": None}
    else:
        failed_attempts[chat_id]["attempts"] += 1

    if failed_attempts[chat_id]["attempts"] >= 3:
        failed_attempts[chat_id]["lockout_until"] = now + timedelta(minutes=30)
        bot.send_message(
            chat_id,
            "Too many failed activation attempts. You have been locked out for 30 minutes."
        )

# --- ANTI-PIRACY & GENERAL COMMANDS ---
@bot.message_handler(func=lambda message: message.chat.type != 'private')
def block_groups(message):
    try:
        bot.leave_chat(message.chat.id)
    except Exception:
        pass

@bot.message_handler(commands=['start', 'menu'])
def show_home(message):
    if message.chat.type != 'private':
        return
    chat_id = str(message.chat.id)
    is_active = check_access(chat_id)
    status_text = "ACTIVE" if is_active else "INACTIVE / EXPIRED"

    text = (
        "*MS RADAR — FOREX STRUCTURE & BIAS*\n"
        "Institutional market structure alerts (D1 → H4).\n\n"
        f"• Account Status: `{status_text}`\n"
        f"• Expiry: `{get_expiry_str(chat_id)}`\n\n"
        "Select an option below:"
    )
    bot.send_message(chat_id, text, reply_markup=build_main_dashboard(is_active), parse_mode="Markdown")

@bot.message_handler(commands=['pairs'])
def open_pairs_cmd(message):
    if message.chat.type != 'private':
        return
    chat_id = str(message.chat.id)
    if not check_access(chat_id):
        show_home(message)
        return
    subs = load_json(config.SUBSCRIPTIONS_FILE)
    user_drafts[chat_id] = set(subs.get(chat_id, []))
    bot.send_message(
        chat_id,
        "*FOREX PAIR CONFIGURATION*\nTap items to toggle, then press *Save Selection*.",
        reply_markup=build_pairs_keyboard(chat_id),
        parse_mode="Markdown"
    )

# --- CALLBACK ROUTERS ---
@bot.callback_query_handler(func=lambda call: call.data == "nav_home")
def cb_home(call):
    chat_id = str(call.message.chat.id)
    is_active = check_access(chat_id)
    status_text = "ACTIVE" if is_active else "INACTIVE / EXPIRED"
    text = (
        "*MS RADAR — FOREX STRUCTURE & BIAS*\n"
        "Institutional market structure alerts (D1 → H4).\n\n"
        f"• Account Status: `{status_text}`\n"
        f"• Expiry: `{get_expiry_str(chat_id)}`\n\n"
        "Select an option below:"
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=build_main_dashboard(is_active), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "nav_plans")
def cb_plans(call):
    text = (
        "*MS RADAR SUBSCRIPTION PLANS*\n\n"
        "*1. Monthly Pass (30 Days)*\n"
        "• Full access to all monitored Forex pairs\n"
        "• Real-time D1 → H4 institutional alerts\n"
        "• Liquidity sweeps & confirmation warnings\n\n"
        "*2. Quarterly Pass (90 Days)*\n"
        "• 3 months uninterrupted delivery\n"
        "• Priority support & bias updates\n\n"
        "Tap *Payment Methods* below to proceed."
    )
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Payment Methods", callback_data="nav_payment_methods"),
        InlineKeyboardButton("Back", callback_data="nav_home")
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "nav_payment_methods")
def cb_payment_methods(call):
    text = "*SELECT PAYMENT METHOD*\n\nChoose your preferred payment method below:"
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Mobile Money", callback_data="pay_momo"),
        InlineKeyboardButton("USDT (TRC20)", callback_data="pay_usdt")
    )
    markup.row(
        InlineKeyboardButton("Enter License Key", callback_data="nav_enter_key"),
        InlineKeyboardButton("Back", callback_data="nav_home")
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "pay_momo")
def cb_momo(call):
    text = (
        "*MOBILE MONEY PAYMENT*\n\n"
        f"1. Send payment to:\n`{MOBILE_MONEY_DETAILS}`\n\n"
        "2. Submit your transaction ID or screenshot to admin.\n\n"
        "3. You will receive an activation code formatted like `MSR-XXXX-XXXX-XXXX`."
    )
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Submit to Admin", url=f"https://t.me/emmas_wrld"),
        InlineKeyboardButton("Enter License Key", callback_data="nav_enter_key")
    )
    markup.add(InlineKeyboardButton("Back", callback_data="nav_payment_methods"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "pay_usdt")
def cb_usdt(call):
    text = (
        "*USDT (TRC20) PAYMENT*\n\n"
        "*Network:* `TRON (TRC20)`\n"
        "*Wallet Address (Tap to copy):*\n"
        f"`{USDT_TRC20_WALLET}`\n\n"
        "⚠️ *Notice:* Send ONLY via TRC20 network. Other networks will lead to loss of funds.\n\n"
        "After transfer, submit your TxID to admin for your activation code."
    )
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Submit TxID", url=f"https://t.me/emmas_wrld"),
        InlineKeyboardButton("Enter License Key", callback_data="nav_enter_key")
    )
    markup.add(InlineKeyboardButton("Back", callback_data="nav_payment_methods"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "nav_enter_key")
def cb_prompt_key(call):
    msg = bot.send_message(
        call.message.chat.id,
        "Please reply with your *license code* (e.g., `MSR-A1B2-C3D4-E5F6`):",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_secure_activation(m, m.text.strip().replace("/activate", "").strip().upper())
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "nav_account")
def cb_account(call):
    chat_id = str(call.message.chat.id)
    subs = load_json(config.SUBSCRIPTIONS_FILE)
    pairs = subs.get(chat_id, [])
    pair_str = "\n".join([f"• {p}" for p in pairs]) if pairs else "_No pairs selected._"

    text = (
        "*ACCOUNT STATUS*\n\n"
        f"• *User ID:* `{chat_id}`\n"
        f"• *Access:* `{'ACTIVE' if check_access(chat_id) else 'EXPIRED'}`\n"
        f"• *Valid Until:* `{get_expiry_str(chat_id)}`\n\n"
        f"*Active Monitored Pairs ({len(pairs)}):*\n{pair_str}"
    )
    markup = InlineKeyboardMarkup()
    if check_access(chat_id):
        markup.add(InlineKeyboardButton("Edit Pairs", callback_data="nav_pairs"))
    else:
        markup.add(InlineKeyboardButton("Renew", callback_data="nav_plans"))
    markup.add(InlineKeyboardButton("Back", callback_data="nav_home"))
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "nav_pairs")
def cb_pairs_menu(call):
    chat_id = str(call.message.chat.id)
    if not check_access(chat_id):
        cb_home(call)
        return
    subs = load_json(config.SUBSCRIPTIONS_FILE)
    user_drafts[chat_id] = set(subs.get(chat_id, []))
    bot.edit_message_text(
        "*FOREX PAIR CONFIGURATION*\nTap items to toggle, then press *Save Selection*.",
        chat_id,
        call.message.message_id,
        reply_markup=build_pairs_keyboard(chat_id),
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("tog_"))
def cb_toggle(call):
    chat_id = str(call.message.chat.id)
    if not check_access(chat_id): return
    idx = int(call.data.split("_")[1])
    pair = FOREX_PAIRS[idx]
    if chat_id not in user_drafts:
        user_drafts[chat_id] = set(load_json(config.SUBSCRIPTIONS_FILE).get(chat_id, []))
    if pair in user_drafts[chat_id]:
        user_drafts[chat_id].remove(pair)
    else:
        user_drafts[chat_id].add(pair)
    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=build_pairs_keyboard(chat_id))

@bot.callback_query_handler(func=lambda call: call.data in ["act_select_all", "act_clear_all"])
def cb_bulk(call):
    chat_id = str(call.message.chat.id)
    if not check_access(chat_id): return
    user_drafts[chat_id] = set(FOREX_PAIRS) if call.data == "act_select_all" else set()
    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=build_pairs_keyboard(chat_id))

@bot.callback_query_handler(func=lambda call: call.data == "act_save")
def cb_save(call):
    chat_id = str(call.message.chat.id)
    if not check_access(chat_id): return
    selected = list(user_drafts.get(chat_id, []))
    subs = load_json(config.SUBSCRIPTIONS_FILE)
    subs[chat_id] = selected
    save_json(config.SUBSCRIPTIONS_FILE, subs)

    text = f"*CONFIGURATION SAVED*\n\nActive markets ({len(selected)}):\n" + "\n".join([f"• {s}" for s in sorted(selected)]) if selected else "*CONFIGURATION SAVED*\n\n_Alerts paused._"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Back to Dashboard", callback_data="nav_home"))
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

if __name__ == "__main__":
    print("[READY] MS Radar (Forex) Secure Listener online...")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"[NETWORK WARNING] Reconnecting in 5s... Error: {e}")
            time.sleep(5)