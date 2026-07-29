# ============================================================
# ===== ТВОИ ДАННЫЕ (ВСТАВЬ СВОИ) =====
BOT_TOKEN = "TOKEN"
OWNER_ID = 
ADMIN_IDS = [OWNER_ID]  # Сюда можно добавить других админов
# ============================================================

import logging
import json
import sqlite3
import random
import time
import csv
from io import BytesIO, StringIO
from datetime import datetime, timedelta
from collections import Counter
import requests

DB_PATH = "bot.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


# ===== БАЗА ДАННЫХ =====
class Database:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                username TEXT,
                crystals INTEGER DEFAULT 0,
                referrer_id INTEGER,
                banned BOOLEAN DEFAULT 0,
                banned_until INTEGER DEFAULT 0,
                muted INTEGER DEFAULT 0,
                muted_until INTEGER DEFAULT 0,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                chat_name TEXT,
                message_text TEXT,
                message_link TEXT,
                message_date TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS referrals (
                referrer_id INTEGER,
                referred_id INTEGER,
                rewarded BOOLEAN DEFAULT 0,
                PRIMARY KEY (referrer_id, referred_id)
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                banned_until TIMESTAMP,
                reason TEXT
            )''')
            conn.commit()

    def add_user(self, user_id, first_name="", last_name="", username="", referrer_id=None):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            if not c.fetchone():
                c.execute('INSERT INTO users (user_id, first_name, last_name, username, referrer_id) VALUES (?, ?, ?, ?, ?)',
                         (user_id, first_name, last_name, username, referrer_id))
                if referrer_id:
                    c.execute('INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)', (referrer_id, user_id))
                conn.commit()
                return True
            return False

    def user_exists(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            return c.fetchone() is not None

    def is_banned(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT banned, banned_until FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            if not row:
                return False
            banned, banned_until = row
            if banned and banned_until and banned_until > 0 and int(time.time()) > banned_until:
                c.execute('UPDATE users SET banned = 0, banned_until = 0 WHERE user_id = ?', (user_id,))
                conn.commit()
                return False
            return bool(banned)

    def add_crystals(self, user_id, amount):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET crystals = crystals + ? WHERE user_id = ?', (amount, user_id))
            conn.commit()

    def get_crystals(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT crystals FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            return row[0] if row else 0

    def set_crystals(self, user_id, amount):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET crystals = ? WHERE user_id = ?', (amount, user_id))
            conn.commit()

    def get_referrer(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT referrer_id FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            return row[0] if row else None

    def is_referrer_rewarded(self, referrer_id, referred_id):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT rewarded FROM referrals WHERE referrer_id = ? AND referred_id = ?', (referrer_id, referred_id))
            row = c.fetchone()
            return row and row[0]

    def mark_referrer_rewarded(self, referrer_id, referred_id):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('UPDATE referrals SET rewarded = 1 WHERE referrer_id = ? AND referred_id = ?', (referrer_id, referred_id))
            conn.commit()

    def increment_usage(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET usage_count = usage_count + 1 WHERE user_id = ?', (user_id,))
            conn.commit()

    def add_message(self, user_id, chat_id, chat_name, message_text, message_link, message_date):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('INSERT INTO messages (user_id, chat_id, chat_name, message_text, message_link, message_date) VALUES (?, ?, ?, ?, ?, ?)',
                     (user_id, chat_id, chat_name, message_text, message_link, message_date))
            conn.commit()

    def count_user_messages(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM messages WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            return row[0] if row else 0

    def get_user_messages(self, user_id, page=1, limit=5):
        offset = (page - 1) * limit
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM messages WHERE user_id = ?', (user_id,))
            total = c.fetchone()[0]
            c.execute('SELECT id, chat_name, message_text, message_link, message_date FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?', (user_id, limit, offset))
            messages = c.fetchall()
            return messages, total

    def get_user_activity(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT usage_count FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            return row[0] if row else 0

    def get_all_users_by_crystals(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT user_id, first_name, last_name, username, crystals FROM users ORDER BY crystals DESC')
            return c.fetchall()

    def count_referrals(self, user_id, since=None):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            if since:
                c.execute('SELECT COUNT(*) FROM users WHERE referrer_id = ? AND created_at > ?', (user_id, since))
            else:
                c.execute('SELECT COUNT(*) FROM users WHERE referrer_id = ?', (user_id,))
            row = c.fetchone()
            return row[0] if row else 0

    def ban_user(self, user_id, duration=None):
        banned_until = int(time.time()) + duration if duration else 0
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET banned = 1, banned_until = ? WHERE user_id = ?', (banned_until, user_id))
            conn.commit()

    def unban_user(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET banned = 0, banned_until = 0 WHERE user_id = ?', (user_id,))
            conn.commit()

    def export_users(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT user_id, first_name, last_name, username, crystals, referrer_id FROM users')
            return c.fetchall()

db = Database()


# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С TELEGRAM API =====
def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        response = requests.post(url, json=payload, timeout=15)
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка send_message: {e}")
        return None

def edit_message_text(chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        response = requests.post(url, json=payload, timeout=15)
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка edit_message_text: {e}")
        return None

def answer_callback(callback_id, text=None, show_alert=False):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    if show_alert:
        payload["show_alert"] = True
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Ошибка answer_callback: {e}")

def get_main_menu(user_id):
    buttons = [
        [{"text": "🔍 Пробив"}],
        [{"text": "💎 Баланс"}],
        [{"text": "🏆 Топ пользователей"}, {"text": "📊 Моя статистика"}],
        [{"text": "🎮 Угадать число"}, {"text": "👥 Рефералы"}],
        [{"text": "📞 Поддержка"}]
    ]
    if user_id == OWNER_ID or user_id in ADMIN_IDS:
        buttons.append([{"text": "📥 Парсинг"}, {"text": "📤 Импорт"}])
    return {"keyboard": buttons, "resize_keyboard": True}

def get_cancel_keyboard():
    return {"inline_keyboard": [[{"text": "❌ Отмена", "callback_data": "cancel_action"}]]}

def get_pagination_keyboard(current_page, total_pages, user_id, prefix="page"):
    buttons = []
    if current_page > 1:
        buttons.append({"text": "⬅️ Назад", "callback_data": f"{prefix}_{user_id}_{current_page-1}"})
    if current_page < total_pages:
        buttons.append({"text": "Вперёд ➡️", "callback_data": f"{prefix}_{user_id}_{current_page+1}"})
    return {"inline_keyboard": [buttons]} if buttons else {}

user_states = {}

# ===== ОБРАБОТЧИКИ =====
def process_start(user_id, first_name, last_name, username):
    logger.info(f"Запуск бота пользователем {user_id}")
    db.increment_usage(user_id)
    
    if not db.user_exists(user_id):
        captcha = random.randint(1000, 9999)
        user_states[user_id] = {"state": "captcha", "captcha": captcha, "attempts": 3}
        send_message(user_id, f"⚠️ Подтвердите, что вы не бот!\n🔑 Код: **{captcha}**\nВведите код (3 попытки) или используйте /cancel")
        return

    referrer_id = db.get_referrer(user_id)
    crystals = db.get_crystals(user_id)
    
    if referrer_id:
        try:
            db.mark_referrer_rewarded(referrer_id, user_id)
        except:
            pass
    
    welcome = (f"🌟 **Добро пожаловать в Testing Bot!** 🌟\n\n"
               f"👤 **Ваш ID:** {user_id}\n"
               f"💎 **Баланс:** {crystals} кристаллов\n"
               f"👥 **Пригласивший:** {referrer_id or 'Нет'}")
    
    send_message(user_id, welcome, reply_markup=get_main_menu(user_id))

def process_captcha_answer(user_id, text):
    if user_id not in user_states or user_states[user_id].get("state") != "captcha":
        return
    
    data = user_states[user_id]
    captcha = data.get("captcha")
    attempts = data.get("attempts", 3)
    
    if text.isdigit() and int(text) == captcha:
        db.add_user(user_id=user_id)
        db.add_crystals(user_id, 100)
        user_states.pop(user_id, None)
        send_message(user_id, "🎉 **Капча пройдена!** Вам начислено 100 кристаллов!", reply_markup=get_main_menu(user_id))
    else:
        attempts -= 1
        if attempts > 0:
            new_captcha = random.randint(1000, 9999)
            user_states[user_id] = {"state": "captcha", "captcha": new_captcha, "attempts": attempts}
            send_message(user_id, f"❌ Неверный код! Осталось попыток: {attempts}\n🔑 Новый код: **{new_captcha}**")
        else:
            db.ban_user(user_id, None)
            user_states.pop(user_id, None)
            send_message(user_id, "🚫 Вы исчерпали все попытки. Вы забанены.")

def process_search(user_id, query):
    crystals = db.get_crystals(user_id)
    if crystals < 2:
        send_message(user_id, "❌ Недостаточно кристаллов! Требуется: 2")
        return
    
    db.add_crystals(user_id, -2)
    user_states[user_id] = {"state": "search", "query": query}
    
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            user_info = None
            try:
                user_id_query = int(query)
                c.execute('SELECT user_id, first_name, last_name, username FROM users WHERE user_id = ?', (user_id_query,))
                user_info = c.fetchone()
            except ValueError:
                c.execute('SELECT user_id, first_name, last_name, username FROM users WHERE username LIKE ?', (f"%{query}%",))
                user_info = c.fetchone()
            
            if not user_info:
                send_message(user_id, "❌ Пользователь не найден", reply_markup=get_main_menu(user_id))
                return
            
            uid, fn, ln, un = user_info
            messages_count = db.count_user_messages(uid)
            response = f"✅ Пользователь: {fn} {ln or ''} (@{un or 'без username'})\n📊 Сообщений: {messages_count}"
            send_message(user_id, response, reply_markup=get_main_menu(user_id))
    except Exception as e:
        send_message(user_id, f"❌ Ошибка: {e}", reply_markup=get_main_menu(user_id))
    
    user_states.pop(user_id, None)

def process_balance(user_id):
    crystals = db.get_crystals(user_id)
    send_message(user_id, f"💎 **Ваш баланс:** {crystals} кристаллов", reply_markup=get_main_menu(user_id))

def process_top_users(user_id, page=1):
    users = db.get_all_users_by_crystals()
    if not users:
        send_message(user_id, "🌟 Топ пока пуст", reply_markup=get_main_menu(user_id))
        return
    per_page = 5
    total_pages = (len(users) + per_page - 1) // per_page
    page_users = users[(page-1)*per_page:page*per_page]
    
    text = f"🏆 **Топ пользователей** (стр. {page}/{total_pages}):\n\n"
    for i, u in enumerate(page_users, (page-1)*per_page):
        name = u[1] or u[3] or str(u[0])
        text += f"**{i+1}.** {name} — 💎 {u[4]}\n"
    
    send_message(user_id, text, reply_markup=get_pagination_keyboard(page, total_pages, user_id))

def process_stats(user_id):
    crystals = db.get_crystals(user_id)
    messages = db.count_user_messages(user_id)
    usage = db.get_user_activity(user_id)
    text = (f"📊 **Ваша статистика:**\n\n"
            f"💎 Баланс: {crystals}\n"
            f"📩 Сообщений: {messages}\n"
            f"⏱ Запусков: {usage}")
    send_message(user_id, text, reply_markup=get_main_menu(user_id))

def process_game_start(user_id):
    number = random.randint(1, 100)
    user_states[user_id] = {"state": "game", "number": number, "attempts": 10}
    send_message(user_id, f"🎮 **Угадай число от 1 до 100!**\nУ вас 10 попыток.", reply_markup=get_cancel_keyboard())

def process_game_guess(user_id, text):
    if user_id not in user_states or user_states[user_id].get("state") != "game":
        return
    
    data = user_states[user_id]
    number = data.get("number")
    attempts = data.get("attempts", 0) - 1
    
    try:
        guess = int(text)
        if guess == number:
            db.add_crystals(user_id, 5)
            user_states.pop(user_id, None)
            send_message(user_id, f"🎉 Угадал! Число {number}. +5 кристаллов!", reply_markup=get_main_menu(user_id))
        elif attempts > 0:
            hint = "⬆ Больше" if guess < number else "⬇ Меньше"
            user_states[user_id] = {"state": "game", "number": number, "attempts": attempts}
            send_message(user_id, f"{hint}\nОсталось {attempts} попыток.")
        else:
            user_states.pop(user_id, None)
            send_message(user_id, f"😞 Игра окончена! Загадано {number}.", reply_markup=get_main_menu(user_id))
    except ValueError:
        send_message(user_id, "⚠️ Введите число!")

def process_referrals(user_id):
    total = db.count_referrals(user_id)
    today = db.count_referrals(user_id, datetime.now() - timedelta(days=1))
    week = db.count_referrals(user_id, datetime.now() - timedelta(days=7))
    
    link = f"https://t.me/TestingBot?start={user_id}"
    text = (f"👥 **Рефералы**\n\n"
            f"🔗 Ссылка: {link}\n"
            f"Сегодня: {today}\n"
            f"Неделя: {week}\n"
            f"Всего: {total}")
    send_message(user_id, text, reply_markup=get_main_menu(user_id))

def process_support(user_id):
    send_message(user_id, "📞 Поддержка: @SupportBot", reply_markup=get_main_menu(user_id))

def process_parse_command(user_id):
    if user_id != OWNER_ID and user_id not in ADMIN_IDS:
        send_message(user_id, "🚫 Доступ только администраторам!")
        return
    user_states[user_id] = {"state": "parse_links"}
    send_message(user_id, "📥 Введите ссылки на чаты (через пробел):", reply_markup=get_cancel_keyboard())

def process_parse_links(user_id, text):
    if user_id not in user_states or user_states[user_id].get("state") != "parse_links":
        return
    links = text.strip().split()
    if not links:
        send_message(user_id, "❌ Введите ссылки!")
        return
    user_states[user_id] = {"state": "parse_limit", "links": links}
    send_message(user_id, "📥 Введите количество сообщений для парсинга (0 - все):")

def process_parse_limit(user_id, text):
    if user_id not in user_states or user_states[user_id].get("state") != "parse_limit":
        return
    try:
        limit = int(text)
        if limit < 0:
            raise ValueError
        send_message(user_id, "⏳ Парсинг запущен...")
        send_message(user_id, "✅ Парсинг завершён!", reply_markup=get_main_menu(user_id))
    except:
        send_message(user_id, "❌ Введите число!", reply_markup=get_cancel_keyboard())
    user_states.pop(user_id, None)

def process_import(user_id):
    if user_id != OWNER_ID and user_id not in ADMIN_IDS:
        send_message(user_id, "🚫 Доступ только администраторам!")
        return
    user_states[user_id] = {"state": "import"}
    send_message(user_id, "📤 Отправьте CSV-файл (user_id,first_name,last_name,username):", reply_markup=get_cancel_keyboard())

def process_give_crystal(user_id, target_id, amount):
    if user_id != OWNER_ID and user_id not in ADMIN_IDS:
        send_message(user_id, "🚫 Доступ только администраторам!")
        return
    db.add_crystals(target_id, amount)
    send_message(user_id, f"✅ Пользователю {target_id} начислено {amount} 💎", reply_markup=get_main_menu(user_id))

def process_set_crystals(user_id, target_id, amount):
    if user_id != OWNER_ID and user_id not in ADMIN_IDS:
        send_message(user_id, "🚫 Доступ только администраторам!")
        return
    db.set_crystals(target_id, amount)
    send_message(user_id, f"✅ Баланс {target_id} установлен на {amount} 💎", reply_markup=get_main_menu(user_id))

def process_command(user_id, text):
    if text.startswith("/givecrystal"):
        parts = text.split()
        if len(parts) == 3:
            try:
                target_id = int(parts[1])
                amount = int(parts[2])
                process_give_crystal(user_id, target_id, amount)
            except:
                send_message(user_id, "❌ Формат: /givecrystal <user_id> <amount>")
        else:
            send_message(user_id, "❌ Формат: /givecrystal <user_id> <amount>")
        return True
    
    if text.startswith("/set_crystals"):
        parts = text.split()
        if len(parts) == 3:
            try:
                target_id = int(parts[1])
                amount = int(parts[2])
                process_set_crystals(user_id, target_id, amount)
            except:
                send_message(user_id, "❌ Формат: /set_crystals <user_id> <amount>")
        else:
            send_message(user_id, "❌ Формат: /set_crystals <user_id> <amount>")
        return True
    
    if text.startswith("/ban"):
        parts = text.split()
        if len(parts) >= 2:
            try:
                target_id = int(parts[1])
                duration = int(parts[2]) if len(parts) > 2 else None
                db.ban_user(target_id, duration)
                send_message(user_id, f"🚫 Пользователь {target_id} забанен!", reply_markup=get_main_menu(user_id))
            except:
                send_message(user_id, "❌ Формат: /ban <user_id> [duration]")
        else:
            send_message(user_id, "❌ Формат: /ban <user_id> [duration]")
        return True
    
    if text.startswith("/unban"):
        parts = text.split()
        if len(parts) == 2:
            try:
                target_id = int(parts[1])
                db.unban_user(target_id)
                send_message(user_id, f"✅ Пользователь {target_id} разблокирован!", reply_markup=get_main_menu(user_id))
            except:
                send_message(user_id, "❌ Формат: /unban <user_id>")
        else:
            send_message(user_id, "❌ Формат: /unban <user_id>")
        return True
    
    return False

def process_message(user_id, text, first_name="", last_name="", username=""):
    db.add_user(user_id=user_id, first_name=first_name, last_name=last_name, username=username)
    
    if db.is_banned(user_id):
        send_message(user_id, "🚫 Вы забанены!")
        return
    
    # Команды
    if text.startswith("/"):
        if process_command(user_id, text):
            return
    
    if user_id in user_states:
        state = user_states[user_id].get("state")
        if state == "captcha":
            process_captcha_answer(user_id, text)
            return
        elif state == "search":
            process_search(user_id, text)
            return
        elif state == "game":
            process_game_guess(user_id, text)
            return
        elif state == "parse_links":
            process_parse_links(user_id, text)
            return
        elif state == "parse_limit":
            process_parse_limit(user_id, text)
            return
        elif state == "cancel":
            user_states.pop(user_id, None)
            send_message(user_id, "❌ Отменено!", reply_markup=get_main_menu(user_id))
            return
    
    if text == "🔍 Пробив":
        user_states[user_id] = {"state": "search"}
        crystals = db.get_crystals(user_id)
        if crystals < 2:
            send_message(user_id, "❌ Недостаточно кристаллов! Требуется: 2", reply_markup=get_main_menu(user_id))
            user_states.pop(user_id, None)
            return
        db.add_crystals(user_id, -2)
        send_message(user_id, "🔍 Введите user_id или username:", reply_markup=get_cancel_keyboard())
    elif text == "💎 Баланс":
        process_balance(user_id)
    elif text == "🏆 Топ пользователей":
        process_top_users(user_id)
    elif text == "📊 Моя статистика":
        process_stats(user_id)
    elif text == "🎮 Угадать число":
        process_game_start(user_id)
    elif text == "👥 Рефералы":
        process_referrals(user_id)
    elif text == "📞 Поддержка":
        process_support(user_id)
    elif text == "📥 Парсинг":
        process_parse_command(user_id)
    elif text == "📤 Импорт":
        process_import(user_id)
    elif text == "/start":
        process_start(user_id, first_name, last_name, username)
    elif text.startswith("/cancel"):
        user_states.pop(user_id, None)
        send_message(user_id, "❌ Отменено!", reply_markup=get_main_menu(user_id))

def process_callback(data, user_id, message_id, chat_id):
    if data == "cancel_action":
        user_states.pop(user_id, None)
        edit_message_text(chat_id, message_id, "❌ Отменено!")
        send_message(user_id, "🌟 Главное меню:", reply_markup=get_main_menu(user_id))
        return
    
    if data.startswith("page_") or data.startswith("top_page_"):
        parts = data.split("_")
        if len(parts) >= 3:
            try:
                page = int(parts[-1])
                if data.startswith("top_page_"):
                    process_top_users(user_id, page)
            except:
                pass
        answer_callback(user_id)


# ===== ПОЛЛИНГ =====
def main():
    logger.info("🚀 Бот запущен!")
    offset = 0
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            response = requests.get(url, params={"offset": offset, "timeout": 30}, timeout=35)
            data = response.json()
            
            if not data.get("ok"):
                logger.error(f"Ошибка API: {data}")
                time.sleep(5)
                continue
            
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                
                if "message" in update:
                    msg = update["message"]
                    chat_id = msg["chat"]["id"]
                    user_id = msg["from"]["id"]
                    text = msg.get("text", "")
                    first_name = msg["from"].get("first_name", "")
                    last_name = msg["from"].get("last_name", "")
                    username = msg["from"].get("username", "")
                    
                    process_message(user_id, text, first_name, last_name, username)
                
                if "callback_query" in update:
                    cb = update["callback_query"]
                    user_id = cb["from"]["id"]
                    data = cb["data"]
                    message_id = cb["message"]["message_id"]
                    chat_id = cb["message"]["chat"]["id"]
                    
                    process_callback(data, user_id, message_id, chat_id)
                    answer_callback(cb["id"])
            
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
