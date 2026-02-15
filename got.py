import telebot
import sqlite3
from datetime import datetime
from telebot import types
import os

TOKEN = os.getenv("TOKEN")
ADMIN_ID = 7070126954

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
    "INSERT OR IGNORE INTO users VALUES (?, 'admin', ?)",
    (ADMIN_ID, "MainAdmin")
)
conn.commit()

# ---------- HELPERS ----------

def ensure_user_exists(user_id):
    cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users VALUES (?, 'user', ?)", (user_id, "User"))
        conn.commit()

def get_admin_ids():
    cursor.execute("SELECT user_id FROM users WHERE role='admin'")
    return [row[0] for row in cursor.fetchall()]

def get_role(user_id):
    cursor.execute("SELECT role FROM users WHERE user_id=?", (user_id,))
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

def log_action(user_id, action, target=""):
    cursor.execute("SELECT nickname FROM users WHERE user_id=?", (user_id,))
    actor = cursor.fetchone()
    actor_name = actor[0] if actor else "Unknown"

    cursor.execute(
        "INSERT INTO logs VALUES (NULL, ?, ?, ?, ?, ?)",
        (user_id, actor_name, action, target, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()

def access_required(func):
    def wrapper(message, *args, **kwargs):
        ensure_user_exists(message.from_user.id)
        role = get_role(message.from_user.id)
        return func(message, role, *args, **kwargs)
    return wrapper

user_states = {}

# ---------- START ----------
@bot.message_handler(commands=["start"])
@access_required
def start(message, role):
    if role == "admin":
        text = "Здорово, а теперь запомни вокруг тебя админы, бот и долбаебы которые стопудово заполнят неправильно описание"
    else:
        text = "Здорово, мозг админам не ебите правильно заполните все по братски)"

    bot.send_message(message.chat.id, text, reply_markup=get_main_keyboard(message.from_user.id))

# ---------- ADD CARD ----------
@bot.message_handler(commands=["addcard"])
@access_required
def addcard(message, role):
    if role == "admin":
        text = ("Вставьте карточку:\n"
                "Имя: ...\nВозраст: ...\nАйди: ...\nЧасовой пояс: ...\nНик: ...\nСтатус: ...\nКомментарий: ...")
    else:
        text = ("Введите данные:\n"
                "Имя:\nВозраст:\nАйди:\nЧасовой пояс:\nНик:")

    bot.send_message(message.chat.id, text, reply_markup=get_main_keyboard(include_cancel=True))
    user_states[message.from_user.id] = {"step": "card", "role": role}

@bot.message_handler(func=lambda m: m.from_user.id in user_states)
def addcard_steps(message):
    user_id = message.from_user.id

    if message.text == "Отмена":
        user_states.pop(user_id, None)
        bot.send_message(message.chat.id, "❌ Отменено", reply_markup=get_main_keyboard(user_id))
        return

    state = user_states[user_id]
    role = state["role"]

    try:
        lines = message.text.split("\n")
        data = {}
        for line in lines:
            if ":" not in line:
                raise ValueError("Неверный формат")
            key, value = line.split(":", 1)
            if not value.strip():
                raise ValueError("Пустое поле")
            data[key.strip().lower()] = value.strip()

        status = data.get("статус", "active🟢")
        comment = data.get("комментарий", "")

        cursor.execute("""
        INSERT INTO cards VALUES (NULL,?,?,?,?,?,?,?,?,?)
        """, (
            data.get("имя"),
            int(data.get("возраст")),
            data.get("айди"),
            data.get("часовой пояс"),
            data.get("ник"),
            status,
            comment,
            user_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        log_action(user_id, "add_card", data.get("ник"))

        bot.send_message(message.chat.id, "✅ Карточка добавлена", reply_markup=get_main_keyboard(user_id))
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {e}", reply_markup=get_main_keyboard(user_id))

    user_states.pop(user_id, None)

# ---------- CHECK ----------
@bot.message_handler(commands=["check"])
@access_required
def check(message, role):
    query = message.text.replace("/check", "").strip()
    if not query:
        bot.send_message(message.chat.id, "Введите ID или ник")
        return

    cursor.execute("SELECT * FROM cards WHERE uid LIKE ? OR nickname LIKE ?", (f"%{query}%", f"%{query}%"))
    rows = cursor.fetchall()
    log_action(message.from_user.id, "check", query)

    if not rows:
        bot.send_message(message.chat.id, "❌ Не найдено")
        return

    for c in rows:
        bot.send_message(message.chat.id,
                         f"{c[1]} | {c[3]} | {c[5]} | {c[6]}")

# ---------- LIST ----------
@bot.message_handler(commands=["list"])
@access_required
def list_cards(message, role):
    cursor.execute("SELECT nickname, uid, status FROM cards")
    rows = cursor.fetchall()

    if not rows:
        bot.send_message(message.chat.id, "База пуста")
        return

    msg = "\n".join([f"{r[0]} | {r[1]} | {r[2]}" for r in rows])
    bot.send_message(message.chat.id, msg)

# ---------- SET STATUS ----------
@bot.message_handler(commands=["setstatus"])
@access_required
def setstatus(message, role):
    if role != "admin":
        bot.send_message(message.chat.id, "Нет доступа")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.send_message(message.chat.id, "Используй: /setstatus ID СТАТУС")
        return

    _, uid, new_status = parts

    cursor.execute("SELECT status FROM cards WHERE uid=?", (uid,))
    row = cursor.fetchone()
    if not row:
        bot.send_message(message.chat.id, "Карточка не найдена")
        return

    old_status = row[0]

    cursor.execute("UPDATE cards SET status=? WHERE uid=?", (new_status, uid))
    cursor.execute("INSERT INTO status_history VALUES (NULL,?,?,?,?,?)",
                   (uid, old_status, new_status, message.from_user.id,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    log_action(message.from_user.id, "setstatus", uid)

    bot.send_message(message.chat.id, "✅ Статус обновлён")

# ---------- LOGS ----------
@bot.message_handler(commands=["logs"])
@access_required
def logs(message, role):
    if role != "admin":
        return

    cursor.execute("SELECT actor, action, target, date FROM logs ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    msg = "\n".join([f"{r[3]} | {r[0]} | {r[1]} | {r[2]}" for r in rows])
    bot.send_message(message.chat.id, msg)

# ---------- BUTTONS ----------
@bot.message_handler(content_types=["text"])
@access_required
def buttons(message, role):
    user_id = message.from_user.id

    if message.text == "Добавить карточку":
        addcard(message, role)

    elif message.text == "Меню" and role == "admin":
        bot.send_message(message.chat.id,
                         "/addcard\n/check\n/history\n/list",
                         reply_markup=get_main_keyboard(user_id))

    elif message.text == "Команды" and role == "admin":
        bot.send_message(message.chat.id,
                         "/setstatus\n/addadmin\n/deladmin\n/logs",
                         reply_markup=get_main_keyboard(user_id))

# ---------- RUN ----------
bot.infinity_polling()
