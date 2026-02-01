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
def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("Меню", "Команды")
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
@access_required
def start(message, role):
    bot.send_message(
        message.chat.id,
        f"🗂 Card Database Bot\nРоль: {role}\n\n"
        "Используйте кнопки внизу или команды:\n"
        "/addcard — добавить карточку\n"
        "/check ID или НИК — поиск\n"
        "/history ID — история статусов\n"
        "/list — список карточек\n\n"
        "Админ:\n"
        "/setstatus ID СТАТУС\n"
        "/addadmin ID НИК\n"
        "/deladmin ID\n"
        "/logs",
        reply_markup=get_main_keyboard()
    )

# ---------- ADD CARD ----------
@bot.message_handler(commands=["addcard"])
@access_required
def addcard(message, role):
    bot.send_message(message.chat.id,
        "Вставьте карточку целиком в формате:\n"
        "Имя: ...\nВозраст: ...\nАйди: ...\nЧасовой пояс: ...\nНик: ...",
        reply_markup=get_main_keyboard()
    )
    user_states[message.from_user.id] = {"step": "wait_card"}

@bot.message_handler(func=lambda m: m.from_user.id in user_states)
def addcard_steps(message):
    state = user_states[message.from_user.id]

    if state.get("step") == "wait_card":
        try:
            lines = message.text.split("\n")
            data = {}
            for line in lines:
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
                data.get("status", "active🟢"),
                data.get("comment", ""),
                message.from_user.id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            log_action(message.from_user.id, "add_card", data.get("ник"))
            bot.send_message(message.chat.id, "✅ Карточка добавлена", reply_markup=get_main_keyboard())
        except Exception as e:
            bot.send_message(message.chat.id, f"⚠️ Ошибка: формат неверный или ID уже есть\n{e}", reply_markup=get_main_keyboard())

        del user_states[message.from_user.id]

# ---------- CHECK (ID + NICKNAME) ----------
@bot.message_handler(commands=["check"])
@access_required
def check(message, role):
    query = " ".join(message.text.split()[1:])
    cursor.execute("""
        SELECT uid, nickname, status FROM cards
        WHERE uid LIKE ? OR nickname LIKE ?
    """, (f"%{query}%", f"%{query}%"))
    rows = cursor.fetchall()
    log_action(message.from_user.id, "check", query)

    if not rows:
        bot.send_message(message.chat.id, "❌ Ничего не найдено", reply_markup=get_main_keyboard())
        return

    if len(rows) == 1:
        uid = rows[0][0]
        cursor.execute("SELECT * FROM cards WHERE uid = ?", (uid,))
        c = cursor.fetchone()
        text = (
            f"🗓 Описание карточки\n\n"
            f"Имя: {c[1]}\n"
            f"Возраст: {c[2]}\n"
            f"Айди: {c[3]}\n"
            f"Часовой пояс: {c[4]}\n"
            f"Ник: {c[5]}\n"
            f"Status: {c[6]}\n"
            f"Комментарий: {c[7]}"
        )
        bot.send_message(message.chat.id, text, reply_markup=get_main_keyboard())
    else:
        msg = "🔍 Найдено несколько:\n\n"
        for r in rows:
            msg += f"{r[5]} | {r[0]} | {r[2]}\n"  # Ник | ID | Статус
        bot.send_message(message.chat.id, msg, reply_markup=get_main_keyboard())

# ---------- HISTORY ----------
@bot.message_handler(commands=["history"])
@access_required
def history(message, role):
    uid = message.text.split()[1]
    cursor.execute("""
        SELECT old_status, new_status, date
        FROM status_history WHERE uid = ?
    """, (uid,))
    rows = cursor.fetchall()

    if not rows:
        bot.send_message(message.chat.id, "📭 История пуста", reply_markup=get_main_keyboard())
        return

    msg = "🔁 История статусов:\n\n"
    for r in rows:
        msg += f"{r[2]}: {r[0]} → {r[1]}\n"

    bot.send_message(message.chat.id, msg, reply_markup=get_main_keyboard())

# ---------- SET STATUS ----------
@bot.message_handler(commands=["setstatus"])
@access_required
def setstatus(message, role):
    if role != "admin":
        return

    _, uid, new_status = message.text.split(maxsplit=2)
    cursor.execute("SELECT status FROM cards WHERE uid = ?", (uid,))
    old_status = cursor.fetchone()[0]

    cursor.execute("UPDATE cards SET status = ? WHERE uid = ?", (new_status, uid))
    cursor.execute("""
        INSERT INTO status_history VALUES (NULL, ?, ?, ?, ?, ?)
    """, (
        uid, old_status, new_status,
        message.from_user.id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    log_action(message.from_user.id, "set_status", uid)

    bot.send_message(message.chat.id, "✅ Статус обновлён", reply_markup=get_main_keyboard())

# ---------- LIST ----------
@bot.message_handler(commands=["list"])
@access_required
def list_cards(message, role):
    cursor.execute("SELECT nickname, uid, status FROM cards")
    rows = cursor.fetchall()

    if not rows:
        bot.send_message(message.chat.id, "📭 База пуста", reply_markup=get_main_keyboard())
        return

    msg = "📋 Карточки:\n\n"
    for r in rows:
        msg += f"{r[0]} | {r[1]} | {r[2]}\n"  # Ник | ID | Статус

    bot.send_message(message.chat.id, msg, reply_markup=get_main_keyboard())

# ---------- LOGS ----------
@bot.message_handler(commands=["logs"])
@access_required
def logs(message, role):
    if role != "admin":
        return

    cursor.execute("""
        SELECT actor, action, target, date
        FROM logs ORDER BY id DESC LIMIT 15
    """)
    rows = cursor.fetchall()

    msg = "🧾 Логи:\n\n"
    for r in rows:
        msg += f"{r[3]} | {r[0]} | {r[1]} | {r[2]}\n"

    bot.send_message(message.chat.id, msg, reply_markup=get_main_keyboard())

# ---------- ADD ADMIN ----------
@bot.message_handler(commands=["addadmin"])
@access_required
def addadmin(message, role):
    if role != "admin":
        return
    try:
        _, uid, nickname = message.text.split(maxsplit=2)
        uid = int(uid)
        cursor.execute("INSERT OR IGNORE INTO users VALUES (?, 'admin', ?)", (uid, nickname))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Админ {nickname} добавлен", reply_markup=get_main_keyboard())
    except:
        bot.send_message(message.chat.id, "⚠️ Ошибка формата команды", reply_markup=get_main_keyboard())

# ---------- DEL ADMIN ----------
@bot.message_handler(commands=["deladmin"])
@access_required
def deladmin(message, role):
    if role != "admin":
        return
    try:
        uid = int(message.text.split()[1])
        cursor.execute("DELETE FROM users WHERE user_id = ?", (uid,))
        conn.commit()
        bot.send_message(message.chat.id, "🗑 Админ удалён", reply_markup=get_main_keyboard())
    except:
        bot.send_message(message.chat.id, "⚠️ Ошибка формата команды", reply_markup=get_main_keyboard())

# ---------- RUN ----------
bot.infinity_polling()
