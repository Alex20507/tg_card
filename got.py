import telebot
import sqlite3
from datetime import datetime
from telebot import types
import os

TOKEN = os.getenv("TOKEN")  # Или вставь прямо токен для проверки
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

# Добавляем главного админа
cursor.execute(
    "INSERT OR IGNORE INTO users (user_id, role, nickname) VALUES (?, 'admin', ?)",
    (ADMIN_ID, "MainAdmin")
)
conn.commit()

# ---------- HELPERS ----------
def get_main_keyboard(role=None, include_cancel=False):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if include_cancel:
        keyboard.row("Отмена")
    else:
        if role == "admin":
            keyboard.row("Меню", "Команды", "Добавить карточку")
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

def get_role(user_id):
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    r = cursor.fetchone()
    return r[0] if r else None

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
def start(message):
    # Авто-добавление нового пользователя
    cursor.execute("SELECT role FROM users WHERE user_id=?", (message.from_user.id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute(
            "INSERT INTO users (user_id, role, nickname) VALUES (?, 'user', ?)",
            (message.from_user.id, message.from_user.first_name)
        )
        conn.commit()
    role = get_role(message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"🗂 Card Database Bot\nРоль: {role}\n\nИспользуйте кнопки внизу или команды",
        reply_markup=get_main_keyboard(role)
    )

# ---------- ADD CARD ----------
@bot.message_handler(commands=["addcard"])
@access_required
def addcard(message, role):
    if role == "admin":
        bot.send_message(
            message.chat.id,
            "Вставьте карточку целиком в формате:\n"
            "Имя: ...\nВозраст: ...\nАйди: ...\nЧасовой пояс: ...\nНик: ...\nСтатус: ...\nКомментарий: ...",
            reply_markup=get_main_keyboard(role, include_cancel=True)
        )
        user_states[message.from_user.id] = {"step": "wait_card_admin", "role": role}
    else:
        bot.send_message(
            message.chat.id,
            "Введите имя:",
            reply_markup=get_main_keyboard(role, include_cancel=True)
        )
        user_states[message.from_user.id] = {"step": "user_add_name", "role": role, "data": {}}

@bot.message_handler(func=lambda m: m.from_user.id in user_states)
def addcard_steps(message):
    if message.text == "Отмена":
        state = user_states[message.from_user.id]
        bot.send_message(message.chat.id, "❌ Действие отменено", reply_markup=get_main_keyboard(state.get("role")))
        del user_states[message.from_user.id]
        return

    state = user_states[message.from_user.id]
    role = state.get("role")

    # --- Админ ---
    if state.get("step") == "wait_card_admin":
        try:
            lines = message.text.split("\n")
            data = {}
            for line in lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    data[key.strip().lower()] = value.strip()

            cursor.execute("""
                INSERT INTO cards (name, age, uid, timezone, nickname, status, comment, added_by, date_added)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("имя"),
                int(data.get("возраст", 0)),
                data.get("айди"),
                data.get("часовой пояс"),
                data.get("ник"),
                data.get("статус", "active🟢"),
                data.get("комментарий", ""),
                message.from_user.id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            log_action(message.from_user.id, "add_card", data.get("ник"))
            bot.send_message(message.chat.id, "✅ Карточка добавлена", reply_markup=get_main_keyboard(role))
        except Exception as e:
            bot.send_message(message.chat.id, f"⚠️ Ошибка: формат неверный или ID уже есть\n{e}", reply_markup=get_main_keyboard(role))
        del user_states[message.from_user.id]

    # --- Обычный пользователь ---
    elif state.get("step", "").startswith("user_add_"):
        data = state.get("data", {})
        if state["step"] == "user_add_name":
            data["name"] = message.text.strip()
            bot.send_message(message.chat.id, "Введите возраст:", reply_markup=get_main_keyboard(role, include_cancel=True))
            state["step"] = "user_add_age"
        elif state["step"] == "user_add_age":
            try:
                data["age"] = int(message.text.strip())
                bot.send_message(message.chat.id, "Введите ID:", reply_markup=get_main_keyboard(role, include_cancel=True))
                state["step"] = "user_add_id"
            except:
                bot.send_message(message.chat.id, "⚠️ Введите число для возраста", reply_markup=get_main_keyboard(role, include_cancel=True))
        elif state["step"] == "user_add_id":
            data["uid"] = message.text.strip()
            bot.send_message(message.chat.id, "Введите часовой пояс:", reply_markup=get_main_keyboard(role, include_cancel=True))
            state["step"] = "user_add_timezone"
        elif state["step"] == "user_add_timezone":
            data["timezone"] = message.text.strip()
            bot.send_message(message.chat.id, "Введите ник:", reply_markup=get_main_keyboard(role, include_cancel=True))
            state["step"] = "user_add_nickname"
        elif state["step"] == "user_add_nickname":
            data["nickname"] = message.text.strip()
            data["status"] = "active🟢"
            data["comment"] = ""
            try:
                cursor.execute("""
                    INSERT INTO cards (name, age, uid, timezone, nickname, status, comment, added_by, date_added)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data["name"], data["age"], data["uid"], data["timezone"],
                    data["nickname"], data["status"], data["comment"],
                    message.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                conn.commit()
                log_action(message.from_user.id, "add_card", data["nickname"])
                bot.send_message(message.chat.id, "✅ Карточка добавлена", reply_markup=get_main_keyboard(role))
            except Exception as e:
                bot.send_message(message.chat.id, f"⚠️ Ошибка: {e}", reply_markup=get_main_keyboard(role))
            del user_states[message.from_user.id]

# ---------- RUN ----------
bot.infinity_polling()
