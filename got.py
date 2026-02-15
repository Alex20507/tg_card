import telebot
from telebot import types
import sqlite3
from datetime import datetime
import os

TOKEN = os.getenv("TOKEN")
bot = telebot.TeleBot(TOKEN)

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

# --- Таблицы ---
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    nickname TEXT,
    role TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    age TEXT,
    uid TEXT UNIQUE,
    timezone TEXT,
    nickname TEXT,
    status TEXT,
    added_by INTEGER,
    date_added TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT,
    action TEXT,
    target TEXT,
    date TEXT
)
""")
conn.commit()

user_states = {}

# --- Роли ---
def get_role(user_id):
    cursor.execute("SELECT role FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else "player"

def get_nick(user_id):
    cursor.execute("SELECT nickname FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else "Неизвестно"

def log_action(user_id, action, target=""):
    actor = get_nick(user_id)
    cursor.execute(
        "INSERT INTO logs (actor, action, target, date) VALUES (?, ?, ?, ?)",
        (actor, action, target, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()

# --- Клавиатуры ---
def player_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ Добавить карточку")
    return kb

def admin_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ Добавить карточку")
    kb.row("📋 Список карточек", "🔍 Поиск")
    kb.row("🛠 Команды")
    return kb

def cancel_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("❌ Отмена")
    return kb

# --- START ---
@bot.message_handler(commands=["start"])
def start(message):
    role = get_role(message.from_user.id)

    if role == "admin":
        bot.send_message(message.chat.id, "👑 Вы администратор", reply_markup=admin_keyboard())
    else:
        bot.send_message(
            message.chat.id,
            "👤 Вы пользователь\nВы можете добавить свою карточку",
            reply_markup=player_keyboard()
        )

# --- Добавление карточки ---
@bot.message_handler(func=lambda m: m.text == "➕ Добавить карточку")
def add_card(message):
    bot.send_message(
        message.chat.id,
        "Вставьте карточку:\n\n"
        "Имя: ...\nВозраст: ...\nАйди: ...\nЧасовой пояс: ...\nНик: ...",
        reply_markup=cancel_keyboard()
    )
    user_states[message.from_user.id] = "waiting_card"

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "waiting_card")
def save_card(message):
    if message.text == "❌ Отмена":
        user_states.pop(message.from_user.id, None)
        start(message)
        return

    try:
        lines = message.text.split("\n")
        data = {}
        for line in lines:
            key, value = line.split(":", 1)
            data[key.strip().lower()] = value.strip()

        cursor.execute("""
            INSERT INTO cards (name, age, uid, timezone, nickname, status, added_by, date_added)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("имя"),
            data.get("возраст"),
            data.get("айди"),
            data.get("часовой пояс"),
            data.get("ник"),
            "active🟢",
            message.from_user.id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()

        log_action(message.from_user.id, "add_card", data.get("ник"))
        bot.send_message(message.chat.id, "✅ Карточка добавлена")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка формата или ID уже существует\n{e}")

    user_states.pop(message.from_user.id, None)
    start(message)

# --- Список карточек (админ) ---
@bot.message_handler(func=lambda m: m.text == "📋 Список карточек")
def list_cards(message):
    if get_role(message.from_user.id) != "admin":
        return

    cursor.execute("SELECT nickname, uid, status FROM cards")
    rows = cursor.fetchall()

    if not rows:
        bot.send_message(message.chat.id, "Список пуст")
        return

    text = "📋 Карточки:\n\n"
    for r in rows:
        text += f"{r[0]} | {r[1]} | {r[2]}\n"

    bot.send_message(message.chat.id, text)

# --- Поиск (админ) ---
@bot.message_handler(func=lambda m: m.text == "🔍 Поиск")
def search_card(message):
    if get_role(message.from_user.id) != "admin":
        return

    bot.send_message(message.chat.id, "Введите ID или ник:")
    user_states[message.from_user.id] = "search"

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "search")
def perform_search(message):
    query = message.text
    cursor.execute("SELECT * FROM cards WHERE uid=? OR nickname=?", (query, query))
    row = cursor.fetchone()

    if row:
        bot.send_message(
            message.chat.id,
            f"Ник: {row[5]}\nИмя: {row[1]}\nВозраст: {row[2]}\nСтатус: {row[6]}"
        )
        log_action(message.from_user.id, "search", row[5])
    else:
        bot.send_message(message.chat.id, "Не найдено")

    user_states.pop(message.from_user.id, None)

# --- Админ-команды ---
@bot.message_handler(func=lambda m: m.text == "🛠 Команды")
def admin_commands(message):
    if get_role(message.from_user.id) != "admin":
        return

    bot.send_message(
        message.chat.id,
        "🛠 Админ команды:\n"
        "/addadmin ID НИК\n"
        "/deladmin ID\n"
        "/logs"
    )

@bot.message_handler(commands=["addadmin"])
def add_admin(message):
    if get_role(message.from_user.id) != "admin":
        return

    try:
        _, uid, nick = message.text.split()
        cursor.execute("INSERT OR REPLACE INTO users VALUES (?, ?, 'admin')", (uid, nick))
        conn.commit()
        bot.send_message(message.chat.id, "Админ добавлен")
    except:
        bot.send_message(message.chat.id, "Формат: /addadmin ID НИК")

@bot.message_handler(commands=["deladmin"])
def del_admin(message):
    if get_role(message.from_user.id) != "admin":
        return

    try:
        _, uid = message.text.split()
        cursor.execute("DELETE FROM users WHERE user_id=?", (uid,))
        conn.commit()
        bot.send_message(message.chat.id, "Админ удалён")
    except:
        bot.send_message(message.chat.id, "Формат: /deladmin ID")

@bot.message_handler(commands=["logs"])
def show_logs(message):
    if get_role(message.from_user.id) != "admin":
        return

    cursor.execute("SELECT actor, action, target, date FROM logs ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()

    text = "🧾 Последние действия:\n\n"
    for r in rows:
        text += f"{r[3]} | {r[0]} | {r[1]} | {r[2]}\n"

    bot.send_message(message.chat.id, text)

bot.infinity_polling()
