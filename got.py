import telebot
import sqlite3
from datetime import datetime
from telebot import types

# ---------- CONFIG ----------
TOKEN = "8365363397:AAEr8RW7eqyH6mFBdfwpe6gZ_8MCpN8n-KU"
ADMIN_ID = 7070126954  # твой ID

bot = telebot.TeleBot(TOKEN)

# ---------- DATABASE ----------
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

# ---------- DATABASE MIGRATION ----------
try:
    cursor.execute("ALTER TABLE logs ADD COLUMN actor TEXT")
except sqlite3.OperationalError:
    pass

# Таблицы
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER UNIQUE,
    role TEXT
)
""")
cursor.execute("INSERT OR IGNORE INTO users VALUES (?, 'admin')", (ADMIN_ID,))

cursor.execute("""
CREATE TABLE IF NOT EXISTS users_nicks (
    user_id INTEGER PRIMARY KEY,
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
    actor TEXT,
    action TEXT,
    target TEXT,
    date TEXT
)
""")

conn.commit()

# ---------- HELPERS ----------
def log_action(user_id, action, target_uid=""):
    # Ник админа
    cursor.execute("SELECT nickname FROM users_nicks WHERE user_id = ?", (user_id,))
    r = cursor.fetchone()
    actor = r[0] if r else f"Admin_{user_id}"

    # Ник игрока
    target = target_uid
    if target_uid:
        cursor.execute("SELECT nickname FROM cards WHERE uid = ?", (target_uid,))
        t = cursor.fetchone()
        if t:
            target = t[0]

    cursor.execute(
        "INSERT INTO logs (actor, action, target, date) VALUES (?, ?, ?, ?)",
        (actor, action, target, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()

def get_role(user_id):
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    r = cursor.fetchone()
    return r[0] if r else None

def access_required(func):
    def wrapper(message):
        role = get_role(message.from_user.id)
        if not role:
            bot.send_message(message.chat.id, "⛔ Нет доступа", reply_markup=main_keyboard())
            return
        return func(message, role)
    return wrapper

# ---------- KEYBOARDS ----------
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("Меню", "Команды")
    return markup

def addcard_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.row("Добавить карточку", "Отмена")
    return markup

user_states = {}

# ---------- START ----------
@bot.message_handler(commands=["start"])
@access_required
def start(message, role):
    bot.send_message(
        message.chat.id,
        f"🗂 Добро пожаловать!\nРоль: {role}\n\nВыберите действие:",
        reply_markup=main_keyboard()
    )

# ---------- MENU BUTTONS ----------
@bot.message_handler(func=lambda m: m.text in ["Меню", "Команды"])
@access_required
def buttons(message, role):
    if message.text == "Меню":
        bot.send_message(message.chat.id, f"Главное меню. Роль: {role}", reply_markup=main_keyboard())
    elif message.text == "Команды":
        bot.send_message(
            message.chat.id,
            "/addcard — добавить карточку\n"
            "/editcard — редактировать карточку\n"
            "/check ID или НИК — поиск\n"
            "/history ID — история статусов\n"
            "/list — список карточек\n\n"
            "Админ:\n"
            "/setstatus ID СТАТУС\n"
            "/adduser ID\n"
            "/deluser ID\n"
            "/addadmin ID НИК\n"
            "/logs",
            reply_markup=main_keyboard()
        )

# ---------- ADD CARD ----------
@bot.message_handler(commands=["addcard"])
@access_required
def addcard(message, role):
    user_states[message.from_user.id] = {"step": "add_card"}
    bot.send_message(
        message.chat.id,
        "📌 Вставь карточку полностью в формате:\n"
        "Имя: ...\nВозраст: ...\nАйди: ...\nЧасовой пояс: ...\nНик: ...\nСтатус: ...\nКомментарий: ...",
        reply_markup=addcard_keyboard()
    )

# ---------- EDIT CARD ----------
@bot.message_handler(commands=["editcard"])
@access_required
def edit_card(message, role):
    user_states[message.from_user.id] = {"step": "edit_id"}
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("Отмена")
    bot.send_message(message.chat.id, "Введите ID карточки, которую хотите редактировать:", reply_markup=markup)

# ---------- ADD ADMIN ----------
@bot.message_handler(commands=["addadmin"])
@access_required
def addadmin(message, role):
    if role != "admin":
        bot.send_message(message.chat.id, "⛔ Только админ может добавлять новых админов", reply_markup=main_keyboard())
        return
    try:
        _, uid, nick = message.text.split(maxsplit=2)
        uid = int(uid)
    except:
        bot.send_message(message.chat.id, "❌ Укажите ID и Ник админа", reply_markup=main_keyboard())
        return
    cursor.execute("INSERT OR REPLACE INTO users VALUES (?, 'admin')", (uid,))
    cursor.execute("INSERT OR REPLACE INTO users_nicks VALUES (?, ?)", (uid, nick))
    conn.commit()
    bot.send_message(message.chat.id, f"✅ ID {uid} теперь админ с ником {nick}", reply_markup=main_keyboard())

# ---------- HANDLE ADD / EDIT STEPS ----------
@bot.message_handler(func=lambda m: m.from_user.id in user_states)
@access_required
def handle_steps(message, role):
    state = user_states[message.from_user.id]

    # Отмена
    if message.text.lower() == "отмена":
        user_states.pop(message.from_user.id, None)
        bot.send_message(message.chat.id, "❌ Операция отменена", reply_markup=main_keyboard())
        return

    # --- ADD CARD ---
    if state.get("step") == "add_card":
        text = message.text.strip()
        lines = text.splitlines()
        data = {}
        for line in lines:
            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip().lower()] = value.strip()
        required = ["имя","возраст","айди","часовой пояс","ник","статус","комментарий"]
        if not all(k in data for k in required):
            bot.send_message(message.chat.id, "❌ Ошибка формата. Проверьте все поля.", reply_markup=addcard_keyboard())
            return
        uid = data["айди"]
        cursor.execute("SELECT id FROM cards WHERE uid = ?", (uid,))
        if cursor.fetchone():
            bot.send_message(message.chat.id, "⚠️ Такой ID уже есть", reply_markup=main_keyboard())
            user_states.pop(message.from_user.id, None)
            return
        cursor.execute("""
            INSERT INTO cards VALUES (NULL,?,?,?,?,?,?,?,?,?)
        """, (
            data["имя"],
            int(data["возраст"]),
            uid,
            data["часовой пояс"],
            data["ник"],
            data["статус"],
            data["комментарий"],
            message.from_user.id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        log_action(message.from_user.id, "add_card", uid)
        bot.send_message(message.chat.id, "✅ Карточка добавлена", reply_markup=main_keyboard())
        user_states.pop(message.from_user.id, None)
        return

    # --- EDIT CARD ---
    if state.get("step") == "edit_id":
        uid = message.text.strip()
        cursor.execute("SELECT * FROM cards WHERE uid = ?", (uid,))
        card = cursor.fetchone()
        if not card:
            bot.send_message(message.chat.id, "❌ Карточка не найдена", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).row("Отмена"))
            return
        state["uid"] = uid
        state["step"] = "edit_card"
        bot.send_message(message.chat.id,
                         "🗓 Текущая карточка:\n"
                         f"Имя: {card[1]}\nВозраст: {card[2]}\nАйди: {card[3]}\nЧасовой пояс: {card[4]}\n"
                         f"Ник: {card[5]}\nСтатус: {card[6]}\nКомментарий: {card[7]}\n\n"
                         "Вставьте карточку с изменениями в том же формате:",
                         reply_markup=addcard_keyboard())
        return

    if state.get("step") == "edit_card":
        text = message.text.strip()
        lines = text.splitlines()
        data = {}
        for line in lines:
            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip().lower()] = value.strip()
        required = ["имя","возраст","айди","часовой пояс","ник","статус","комментарий"]
        if not all(k in data for k in required):
            bot.send_message(message.chat.id, "❌ Ошибка формата.", reply_markup=addcard_keyboard())
            return
        old_uid = state["uid"]
        new_uid = data["айди"]
        if new_uid != old_uid:
            cursor.execute("SELECT id FROM cards WHERE uid = ?", (new_uid,))
            if cursor.fetchone():
                bot.send_message(message.chat.id, "⚠️ Такой новый ID уже есть.", reply_markup=addcard_keyboard())
                return
        cursor.execute("""
            UPDATE cards SET name=?, age=?, uid=?, timezone=?, nickname=?, status=?, comment=? WHERE uid=?
        """, (
            data["имя"], int(data["возраст"]), new_uid, data["часовой пояс"], data["ник"], data["статус"], data["комментарий"], old_uid
        ))
        conn.commit()
        log_action(message.from_user.id, "edit_card", new_uid)
        bot.send_message(message.chat.id, "✅ Карточка обновлена", reply_markup=main_keyboard())
        user_states.pop(message.from_user.id, None)

# ---------- CHECK ----------
@bot.message_handler(commands=["check"])
@access_required
def check(message, role):
    query = " ".join(message.text.split()[1:])
    cursor.execute("SELECT uid, nickname, status FROM cards WHERE uid LIKE ? OR nickname LIKE ?", (f"%{query}%", f"%{query}%"))
    rows = cursor.fetchall()
    log_action(message.from_user.id, "check", query)
    if not rows:
        bot.send_message(message.chat.id, "❌ Ничего не найдено")
        return
    if len(rows) == 1:
        uid = rows[0][0]
        cursor.execute("SELECT * FROM cards WHERE uid = ?", (uid,))
        c = cursor.fetchone()
        text = (
            "🗓 Описание карточки\n\n"
            f"Имя: {c[1]}\nВозраст: {c[2]}\nАйди: {c[3]}\nЧасовой пояс: {c[4]}\n"
            f"Ник: {c[5]}\nСтатус: {c[6]}\nКомментарий: {c[7]}"
        )
        bot.send_message(message.chat.id, text)
    else:
        msg = "🔍 Найдено несколько:\n\n"
        for r in rows:
            msg += f"{r[1]} | {r[0]} | {r[2]}\n"
        bot.send_message(message.chat.id, msg)

# ---------- HISTORY ----------
@bot.message_handler(commands=["history"])
@access_required
def history(message, role):
    uid = message.text.split()[1]
    cursor.execute("SELECT old_status, new_status, date FROM status_history WHERE uid = ?", (uid,))
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "📭 История пуста")
        return
    msg = "🔁 История статусов:\n\n"
    for r in rows:
        msg += f"{r[2]}: {r[0]} → {r[1]}\n"
    bot.send_message(message.chat.id, msg)

# ---------- SET STATUS ----------
@bot.message_handler(commands=["setstatus"])
@access_required
def setstatus(message, role):
    if role != "admin":
        return
    try:
        _, uid, new_status = message.text.split(maxsplit=2)
    except:
        bot.send_message(message.chat.id, "❌ Укажите ID и новый статус", reply_markup=main_keyboard())
        return
    cursor.execute("SELECT status FROM cards WHERE uid = ?", (uid,))
    old_status = cursor.fetchone()[0]
    cursor.execute("UPDATE cards SET status = ? WHERE uid = ?", (new_status, uid))
    cursor.execute("INSERT INTO status_history VALUES (NULL, ?, ?, ?, ?, ?)", (
        uid, old_status, new_status, message.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    log_action(message.from_user.id, f"set_status -> {new_status}", uid)
    bot.send_message(message.chat.id, "✅ Статус обновлён", reply_markup=main_keyboard())

# ---------- LIST ----------
@bot.message_handler(commands=["list"])
@access_required
def list_cards(message, role):
    cursor.execute("SELECT nickname, uid, status FROM cards")
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "📭 База пуста")
        return
    msg = "📋 Карточки:\n\n"
    for r in rows:
        msg += f"{r[0]} | {r[1]} | {r[2]}\n"
    bot.send_message(message.chat.id, msg)

# ---------- LOGS ----------
@bot.message_handler(commands=["logs"])
@access_required
def logs(message, role):
    if role != "admin":
        return
    cursor.execute("SELECT actor, action, target, date FROM logs ORDER BY id DESC LIMIT 15")
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "📭 Логи пусты")
        return
    msg = "🧾 Логи:\n\n"
    for r in rows:
        actor = r[0] if r[0] else "Неизвестно"
        action = r[1] if r[1] else "-"
        target = r[2] if r[2] else "-"
        date = r[3] if r[3] else "-"
        msg += f"{date} | {actor} | {action} | {target}\n"
    bot.send_message(message.chat.id, msg)

# ---------- USERS ----------
@bot.message_handler(commands=["adduser"])
@access_required
def adduser(message, role):
    if role != "admin":
        return
    uid = int(message.text.split()[1])
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, 'user')", (uid,))
    conn.commit()
    bot.send_message(message.chat.id, "✅ Доступ выдан", reply_markup=main_keyboard())

@bot.message_handler(commands=["deluser"])
@access_required
def deluser(message, role):
    if role != "admin":
        return
    uid = int(message.text.split()[1])
    cursor.execute("DELETE FROM users WHERE user_id = ?", (uid,))
    conn.commit()
    bot.send_message(message.chat.id, "🗑 Доступ удалён", reply_markup=main_keyboard())

# ---------- RUN ----------
bot.infinity_polling()
