import telebot
import sqlite3
from datetime import datetime
from telebot import types
import os

TOKEN = os.getenv("TOKEN")  # Токен берётся из переменных окружения
ADMIN_ID = 7070126954  # Твой Telegram ID для первого админа

bot = telebot.TeleBot(TOKEN)

# ---------- DATABASE ----------
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER UNIQUE,
    role TEXT,
    nickname TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    age INTEGER,
    uid TEXT UNIQUE,
    timezone TEXT,
    nickname TEXT,
    status TEXT,
    comment TEXT,
    added_by INTEGER,
    date_added TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT,
    old_status TEXT,
    new_status TEXT,
    changed_by INTEGER,
    date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    actor TEXT,
    action TEXT,
    target TEXT,
    date TEXT
)
""")

cursor.execute(
    "INSERT OR IGNORE INTO users (user_id, role, nickname) VALUES (?, 'admin', ?)",
    (ADMIN_ID, "MainAdmin")
)
conn.commit()

# ---------- HELPERS ----------
def get_admin_ids():
    cursor.execute("SELECT user_id FROM users WHERE role='admin'")
    return [row[0] for row in cursor.fetchall()]

def get_role(user_id):
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    r = cursor.fetchone()
    return r[0] if r else None

def get_main_keyboard(user_id=None, include_cancel=False):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if include_cancel:
        keyboard.row("Отмена")
    else:
        if user_id in get_admin_ids():
            keyboard.row("Меню", "Команды")
        else:
            keyboard.row("Добавить карточку")
    return keyboard

def log_action(user_id, action, target_nickname=""):
    cursor.execute("SELECT nickname FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    actor_nick = row[0] if row else "Неизвестно"

    cursor.execute(
        "INSERT INTO logs (user_id, actor, action, target, date) VALUES (?, ?, ?, ?, ?)",
        (user_id, actor_nick, action, target_nickname, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()

def access_required(func):
    def wrapper(message, *args, **kwargs):
        role = get_role(message.from_user.id)
        if not role:
            bot.send_message(message.chat.id, "⛔ Нет доступа", reply_markup=get_main_keyboard())
            return
        return func(message, role, *args, **kwargs)
    return wrapper

user_states = {}

# ---------- START ----------
@bot.message_handler(commands=["start"])
@access_required
def start(message, role):
    bot.send_message(
        message.chat.id,
        f"🗂 Card Database Bot\nРоль: {role}",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

# ---------- ADD CARD ----------
@bot.message_handler(commands=["addcard"])
@access_required
def addcard(message, role):
    if role == "admin":
        text = ("Вставьте карточку целиком в формате (админ):\n"
                "Имя: ...\nВозраст: ...\nАйди: ...\nЧасовой пояс: ...\nНик: ...\nСтатус: ...\nКомментарий: ...")
    else:
        text = ("Вставьте карточку целиком в формате:\n"
                "Имя: ...\nВозраст: ...\nАйди: ...\nЧасовой пояс: ...\nНик: ...")
    bot.send_message(
        message.chat.id,
        text,
        reply_markup=get_main_keyboard(include_cancel=True)
    )
    user_states[message.from_user.id] = {"step": "wait_card", "role": role}

@bot.message_handler(func=lambda m: m.from_user.id in user_states)
def addcard_steps(message):
    if message.text == "Отмена":
        bot.send_message(message.chat.id, "❌ Действие отменено", reply_markup=get_main_keyboard(message.from_user.id))
        del user_states[message.from_user.id]
        return

    state = user_states[message.from_user.id]
    role = state.get("role")

    if state.get("step") == "wait_card":
        try:
            lines = message.text.split("\n")
            data = {}
            for line in lines:
                key, value = line.split(":", 1)
                data[key.strip().lower()] = value.strip()

            status_value = data.get("статус") if role == "admin" else "active🟢"
            comment_value = data.get("комментарий") if role == "admin" else ""

            cursor.execute("""
                INSERT INTO cards (name, age, uid, timezone, nickname, status, comment, added_by, date_added)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("имя"),
                int(data.get("возраст", 0)),
                data.get("айди"),
                data.get("часовой пояс"),
                data.get("ник"),
                status_value,
                comment_value,
                message.from_user.id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            log_action(message.from_user.id, "add_card", data.get("ник"))
            bot.send_message(message.chat.id, "✅ Карточка добавлена", reply_markup=get_main_keyboard(message.from_user.id))
        except Exception as e:
            bot.send_message(message.chat.id, f"⚠️ Ошибка: формат неверный или ID уже есть\n{e}", reply_markup=get_main_keyboard(message.from_user.id))

        del user_states[message.from_user.id]

# ---------- BUTTONS HANDLER ----------
@bot.message_handler(func=lambda m: True)
@access_required
def buttons_handler(message, role):
    user_id = message.from_user.id
    if message.text == "Меню":
        msg = "📌 Главное меню:\n/addcard — добавить карточку\n/check ID или НИК — поиск карточки\n/history ID — история статусов\n/list — список карточек"
        bot.send_message(message.chat.id, msg, reply_markup=get_main_keyboard(user_id))
    elif message.text == "Команды":
        msg = "📋 Все команды:\n/addcard — добавить карточку\n/check ID или НИК — поиск карточки\n/history ID — история статусов\n/list — список карточек\n"
        if role == "admin":
            msg += "/setstatus ID СТАТУС — изменить статус\n/addadmin ID НИК — добавить админа\n/deladmin ID — удалить админа\n/logs — логи"
        bot.send_message(message.chat.id, msg, reply_markup=get_main_keyboard(user_id))
    elif message.text == "Добавить карточку":
        addcard(message, role)
    elif message.text == "Отмена":
        bot.send_message(message.chat.id, "❌ Действие отменено", reply_markup=get_main_keyboard(user_id))

# ---------- RUN ----------
bot.infinity_polling()
