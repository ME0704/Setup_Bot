import os
import json
import time
import secrets
from datetime import datetime, timedelta
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
import config

# Token resolution
TOKEN = (
    getattr(config, "TELEGRAM_BOT_TOKEN", None)
    or os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv(getattr(config, "TELEGRAM_TOKEN_ENV", ""), "")
)

if not TOKEN:
    raise ValueError("Telegram Bot Token not found! Ensure TELEGRAM_BOT_TOKEN is set in your .env file.")

bot = telebot.TeleBot(TOKEN)

# Dynamic symbol resolution
FOREX_PAIRS = getattr(config, "PAIRS", getattr(config, "SYMBOLS", []))

# Memory buffers
user_drafts = {}
failed_attempts = {}

# --- ADMIN & PAYMENT DETAILS (UPDATE THESE) ---
ADMIN_TELEGRAM_USERNAME = "emmas_wrld"  # Admin handle without '@'
MOBILE_MONEY_DETAILS = "MTN / Airtel: +256 704 598 003  (Name: MODI EMMANUEL)"
USDT_TRC20_WALLET = "TYOURTRC20WALLETADDRESSHERE"

# --- REGISTER TELEGRAM MENU BUTTON ---
def register_bot_commands():
    """Adds the permanent 'Menu' button next to the chat text bar."""
    try:
        commands = [
            BotCommand("start", "Main Dashboard & Overview"),
            BotCommand("pairs", "Configure Monitored Pairs"),
            BotCommand("account", "Check Subscription Status"),
            BotCommand("help", "Pricing & Payment Guide")
        ]
        bot.set_my_commands(commands)
    except Exception as e:
        print(f"[WARNING] Could not register menu commands: {e}")

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
            InlineKeyboardButton("1. Plans & Pricing", callback_data="nav_plans"),
            InlineKeyboardButton("2. Payment Methods", callback_data="nav_payment_methods")
        )
        markup.row(
            InlineKeyboardButton("3. Enter License Key", callback_data="nav_enter_key"),
            InlineKeyboardButton("My Status", callback_data="nav_account")
        )
        markup.add(
            InlineKeyboardButton("Contact Admin / Submit Proof", url=f"https://t.me/{ADMIN_TELEGRAM_USERNAME}")
        )
    return markup

def build_pairs_keyboard(chat_id: str) -> InlineKeyboardMarkup:
    selected_set = user_drafts.get(chat_id, set())
    markup = InlineKeyboardMarkup()
    
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

# --- ADMIN KEY GENERATOR ---
@bot.message_handler(commands=['genkey'])
def generate_key(message):
    chat_id = str(message.chat.id)
    if chat_id != str(config.ADMIN_CHAT_ID):
        return

    parts = message.text.split()
    days = 30
    assigned_target = None

    if len(parts) >= 2:
        try:
            days = int(parts[1])
        except ValueError:
            bot.reply_to(message, "Usage: `/genkey <days> [@username or chat_id]`", parse_mode="Markdown")
            return

    if len(parts) >= 3:
        assigned_target = parts[2].replace("@", "").strip().lower()

    raw = secrets.token_hex(6).upper()
    new_key = f"MSR-{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"

    keys_db = load_json(config.KEYS_DB)
    keys_db[new_key] = {
        "days": days,
        "assigned_to": assigned_target,
        "used": False,
        "used_by": None,
        "created_at": datetime.now().isoformat()
    }
    save_json(config.KEYS_DB, keys_db)

    target_text = f"Bound to: `@{assigned_target}`" if assigned_target else "Status: `Unbound (Any account can activate)`"
    bot.reply_to(
        message,
        f"*MS RADAR LICENSE GENERATED*\n\nKey: `{new_key}`\nDuration: `{days} Days`\n{target_text}",
        parse_mode="Markdown"
    )

# --- USER ACTIVATION ---
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

    if chat_id in failed_attempts:
        lockout = failed_attempts[chat_id].get("lockout_until")
        if lockout and now < lockout:
            wait_min = int((lockout - now).total_seconds() / 60) + 1
            bot.send_message(chat_id, f"Account locked due to failed attempts. Retry in {wait_min} minutes.")
            return

    keys_db = load_json(config.KEYS_DB)
    if entered_key not in keys_db:
        record_failed_attempt(chat_id)
        bot.send_message(chat_id, "Invalid activation key. Please verify the code and try again.")
        return

    key_record = keys_db[entered_key]
    if key_record["used"]:
        bot.send_message(chat_id, "This license key has already been redeemed.")
        return

    bound_target = key_record.get("assigned_to")
    if bound_target:
        if bound_target != username and bound_target != chat_id:
            bot.send_message(chat_id, "Unauthorized: This key is cryptographically assigned to another Telegram account.")
            return

    if chat_id in failed_attempts:
        del failed_attempts[chat_id]

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

    key_record["used"] = True
    key_record["used_by"] = chat_id
    key_record["redeemed_by_username"] = username or None
    key_record["redeemed_at"] = now.isoformat()
    save_json(config.KEYS_DB, keys_db)

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Configure Pairs", callback_data="nav_pairs"))
    bot.send_message(
        chat_id,
        f"✅ *MS RADAR ACCESS ACTIVATED*\n\n"
        f"• Duration: `{days_to_add} Days`\n"
        f"• Expiration: `{new_expiry.strftime('%Y-%m-%d %H:%M EAT')}`\n\n"
        f"Tap below to select your monitored forex pairs.",
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
        bot.send_message(chat_id, "Too many failed activation attempts. You are locked out for 30 minutes.")

# --- PRIVATE CHAT LOCKDOWN ---
@bot.message_handler(func=lambda message: message.chat.type != 'private')
def block_groups(message):
    try:
        bot.leave_chat(message.chat.id)
    except Exception:
        pass

# --- CORE DASHBOARD & INTRO ---
@bot.message_handler(commands=['start', 'menu', 'help'])
def show_home(message):
    if message.chat.type != 'private':
        return
    chat_id = str(message.chat.id)
    is_active = check_access(chat_id)
    status_text = "ACTIVE" if is_active else "INACTIVE / EXPIRED"

    if is_active:
        text = (
            "*MS RADAR — ACTIVE DASHBOARD*\n\n"
            "Your institutional alert engine is online and monitoring your selected pairs.\n\n"
            f"• *Account Status:* `{status_text}`\n"
            f"• *Valid Until:* `{get_expiry_str(chat_id)}`\n\n"
            "Tap *Configure Pairs* below to update your monitored watchlist, or *My Account* to review your subscription."
        )
    else:
        text = (
            "*MS RADAR — INSTITUTIONAL FOREX INTELLIGENCE*\n\n"
            "Welcome to MS Radar. This system tracks institutional market structure across currency pairs, "
            "filtering market noise using multi-timeframe breakout models (D1 → H4).\n\n"
            "*Core Services Provided:*\n"
            "• Real-time D1 → H4 breakout and change-of-character alerts\n"
            "• Liquidity sweep detection (A+ grade trade qualifications)\n"
            "• Adverse extreme warnings (prior-day high/low invalidation)\n"
            "• Fully customizable per-pair alert filters\n\n"
            f"*Account Overview:*\n"
            f"• Status: `{status_text}`\n"
            f"• Access Until: `{get_expiry_str(chat_id)}`\n\n"
            "Follow the steps below to subscribe or configure your watchlist:"
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
        "*FOREX PAIR CONFIGURATION*\nTap any pair to toggle alerts on or off, then tap *Save Selection*.",
        reply_markup=build_pairs_keyboard(chat_id),
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['account'])
def open_account_cmd(message):
    if message.chat.type != 'private':
        return
    chat_id = str(message.chat.id)
    cb_account_direct(chat_id)

def cb_account_direct(chat_id: str, message_id: int = None):
    subs = load_json(config.SUBSCRIPTIONS_FILE)
    pairs = subs.get(chat_id, [])
    pair_str = "\n".join([f"• {p}" for p in pairs]) if pairs else "_No pairs selected._"

    text = (
        "*ACCOUNT STATUS*\n\n"
        f"• *User ID:* `{chat_id}`\n"
        f"• *Access:* `{'ACTIVE' if check_access(chat_id) else 'EXPIRED'}`\n"
        f"• *Valid Until:* `{get_expiry_str(chat_id)}`\n\n"
        f"*Monitored Pairs ({len(pairs)}):*\n{pair_str}"
    )
    markup = InlineKeyboardMarkup()
    if check_access(chat_id):
        markup.add(InlineKeyboardButton("Edit Pairs", callback_data="nav_pairs"))
    else:
        markup.add(InlineKeyboardButton("View Plans & Renew", callback_data="nav_plans"))
    markup.add(InlineKeyboardButton("Back to Dashboard", callback_data="nav_home"))

    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

# --- CALLBACK ROUTERS ---
@bot.callback_query_handler(func=lambda call: call.data == "nav_home")
def cb_home(call):
    bot.answer_callback_query(call.id)
    chat_id = str(call.message.chat.id)
    is_active = check_access(chat_id)
    status_text = "ACTIVE" if is_active else "INACTIVE / EXPIRED"

    text = (
        "*MS RADAR — INSTITUTIONAL FOREX INTELLIGENCE*\n\n"
        "Welcome to MS Radar. This system tracks institutional market structure across currency pairs, "
        "filtering market noise using multi-timeframe breakout models (D1 → H4).\n\n"
        "*Core Services Provided:*\n"
        "• Real-time D1 → H4 breakout alerts\n"
        "• Liquidity sweep detection (A+ grade trade qualifications)\n"
        "• Adverse extreme warnings\n"
        "• Individual pair watchlist customization\n\n"
        f"*Account Overview:*\n"
        f"• Status: `{status_text}`\n"
        f"• Access Until: `{get_expiry_str(chat_id)}`\n\n"
        "Follow the steps below to subscribe or configure your watchlist:"
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=build_main_dashboard(is_active), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "nav_plans")
def cb_plans(call):
    bot.answer_callback_query(call.id)
    text = (
        "*MS RADAR — PRICING PLANS*\n\n"
        "*1. Monthly License (30 Days)*\n"
        "• Full access to all monitored Forex pairs\n"
        "• Real-time D1 → H4 structure breakout alerts\n"
        "• Liquidity sweeps & confirmation warnings\n\n"
        "*2. Quarterly License (90 Days)*\n"
        "• 3 months of uninterrupted signals\n"
        "• Priority support & bias updates\n\n"
        "Select your preferred payment method below to get started:"
    )
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Payment Methods", callback_data="nav_payment_methods"),
        InlineKeyboardButton("Back", callback_data="nav_home")
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "nav_payment_methods")
def cb_payment_methods(call):
    bot.answer_callback_query(call.id)
    text = (
        "*STEP 2: CHOOSE PAYMENT METHOD*\n\n"
        "Select an option below to view transfer details and payment instructions:"
    )
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Mobile Money", callback_data="pay_momo"),
        InlineKeyboardButton("USDT (TRC20)", callback_data="pay_usdt")
    )
    markup.row(
        InlineKeyboardButton("I Already Have a Code", callback_data="nav_enter_key"),
        InlineKeyboardButton("Back", callback_data="nav_home")
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "pay_momo")
def cb_momo(call):
    bot.answer_callback_query(call.id)
    text = (
        "*MOBILE MONEY PAYMENT GUIDE*\n\n"
        "*Step 1: Transfer Funds*\n"
        f"Send the fee to the account below:\n`{MOBILE_MONEY_DETAILS}`\n\n"
        "*Step 2: Save Your Receipt*\n"
        "Keep the transaction ID or take a screenshot of the confirmation SMS.\n\n"
        "*Step 3: Submit Payment Proof*\n"
        "Tap the button below to message admin directly with your proof.\n\n"
        "*Step 4: Activate*\n"
        "Admin will send your activation code. Tap *Enter License Key* to start receiving alerts."
    )
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Submit Payment Proof", url=f"https://t.me/{ADMIN_TELEGRAM_USERNAME}"),
        InlineKeyboardButton("Enter License Key", callback_data="nav_enter_key")
    )
    markup.add(InlineKeyboardButton("Back to Payment Methods", callback_data="nav_payment_methods"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "pay_usdt")
def cb_usdt(call):
    bot.answer_callback_query(call.id)
    text = (
        "*USDT (TRC20) PAYMENT GUIDE*\n\n"
        "*Network:* `TRON (TRC20)`\n"
        "*Deposit Address (Tap to Copy):*\n"
        f"`{USDT_TRC20_WALLET}`\n\n"
        "⚠️ *Notice:* Transfer strictly via the TRC20 network. Any other network will result in unrecoverable funds.\n\n"
        "*Next Steps:*\n"
        "1. Complete the transfer in your crypto wallet.\n"
        "2. Copy the Transaction Hash (TxID) or screenshot.\n"
        "3. Tap *Submit TxID to Admin* below to confirm.\n"
        "4. You will receive an activation code formatted like `MSR-XXXX-XXXX-XXXX`."
    )
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Submit TxID to Admin", url=f"https://t.me/{ADMIN_TELEGRAM_USERNAME}"),
        InlineKeyboardButton("Enter License Key", callback_data="nav_enter_key")
    )
    markup.add(InlineKeyboardButton("Back to Payment Methods", callback_data="nav_payment_methods"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "nav_enter_key")
def cb_prompt_key(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        "Please reply with your *license code* (e.g., `MSR-A1B2-C3D4-E5F6`):",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_secure_activation(m, m.text.strip().replace("/activate", "").strip().upper())
    )

@bot.callback_query_handler(func=lambda call: call.data == "nav_account")
def cb_account(call):
    bot.answer_callback_query(call.id)
    cb_account_direct(str(call.message.chat.id), call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "nav_pairs")
def cb_pairs_menu(call):
    bot.answer_callback_query(call.id)
    chat_id = str(call.message.chat.id)
    if not check_access(chat_id):
        cb_home(call)
        return
    subs = load_json(config.SUBSCRIPTIONS_FILE)
    user_drafts[chat_id] = set(subs.get(chat_id, []))
    bot.edit_message_text(
        "*FOREX PAIR CONFIGURATION*\nTap any pair to toggle alerts on or off, then tap *Save Selection*.",
        chat_id,
        call.message.message_id,
        reply_markup=build_pairs_keyboard(chat_id),
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("tog_"))
def cb_toggle(call):
    chat_id = str(call.message.chat.id)
    if not check_access(chat_id):
        bot.answer_callback_query(call.id)
        return
    idx = int(call.data.split("_")[1])
    pair = FOREX_PAIRS[idx]
    if chat_id not in user_drafts:
        user_drafts[chat_id] = set(load_json(config.SUBSCRIPTIONS_FILE).get(chat_id, []))
    if pair in user_drafts[chat_id]:
        user_drafts[chat_id].remove(pair)
    else:
        user_drafts[chat_id].add(pair)
    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=build_pairs_keyboard(chat_id))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data in ["act_select_all", "act_clear_all"])
def cb_bulk(call):
    chat_id = str(call.message.chat.id)
    if not check_access(chat_id):
        bot.answer_callback_query(call.id)
        return
    user_drafts[chat_id] = set(FOREX_PAIRS) if call.data == "act_select_all" else set()
    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=build_pairs_keyboard(chat_id))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "act_save")
def cb_save(call):
    chat_id = str(call.message.chat.id)
    if not check_access(chat_id):
        bot.answer_callback_query(call.id)
        return
    selected = list(user_drafts.get(chat_id, []))
    subs = load_json(config.SUBSCRIPTIONS_FILE)
    subs[chat_id] = selected
    save_json(config.SUBSCRIPTIONS_FILE, subs)

    text = f"*CONFIGURATION SAVED*\n\nActive markets ({len(selected)}):\n" + "\n".join([f"• {s}" for s in sorted(selected)]) if selected else "*CONFIGURATION SAVED*\n\n_Alerts paused._"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Back to Dashboard", callback_data="nav_home"))
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    bot.answer_callback_query(call.id, text="Saved!")

if __name__ == "__main__":
    print("[INIT] Registering Telegram command menu...")
    register_bot_commands()
    print("[READY] MS Radar (Forex) Listener online. Polling...")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"[NETWORK WARNING] Reconnecting in 5s... Error: {e}")
            time.sleep(5)