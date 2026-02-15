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

user_states = {}

# ---------- START ----------
@bot.message_handler(commands=["start"])
def start(message):
    role = get_role(message.from_user.id)
    if not role:
        cursor.execute(
            "INSERT INTO users (user_id, role, nickname) VALUES (?, 'user', ?)",
            (message.from_user.id, message.from_user.first_name)
        )
        conn.commit()
        role = "user"

    if role == "admin":
        text = "Здорово, а теперь запомни: вокруг тебя админы, бот и долбаебы, которые стопудово заполнят неправильно описание 😎"
    else:
        text = "Здорово, мозг админам не ебите 🙂 Правильно заполните все, по братски!"
    bot.send_message(message.chat.id, text, reply_markup=get_main_keyboard(role))

# ---------- ADD CARD ----------
@bot.message_handler(commands=["addcard"])
def addcard(message):
    role = get_role(message.from_user.id)
    if not role:
        bot.send_message(message.chat.id, "⛔ Нет доступа")
        return

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

# ---------- ADMIN COMMANDS (Пошаговые) ----------
def start_admin_step(message, step_name, prompt):
    user_states[message.from_user.id] = {"step": step_name, "role": "admin", "data": {}}
    bot.send_message(message.chat.id, prompt, reply_markup=get_main_keyboard("admin", include_cancel=True))

@bot.message_handler(commands=["check"])
def check_command(message):
    role = get_role(message.from_user.id)
    if role != "admin":
        bot.send_message(message.chat.id, "⛔ Нет доступа")
        return
    start_admin_step(message, "check_id", "Введите ID или Ник для поиска карточки:")

@bot.message_handler(commands=["history"])
def history_command(message):
    role = get_role(message.from_user.id)
    if role != "admin":
        bot.send_message(message.chat.id, "⛔ Нет доступа")
        return
    start_admin_step(message, "history_id", "Введите ID карточки для истории:")

@bot.message_handler(commands=["setstatus"])
def setstatus_command(message):
    role = get_role(message.from_user.id)
    if role != "admin":
        bot.send_message(message.chat.id, "⛔ Нет доступа")
        return
    start_admin_step(message, "setstatus_id", "Введите ID карточки, чтобы изменить статус:")

@bot.message_handler(commands=["addadmin"])
def addadmin_command(message):
    role = get_role(message.from_user.id)
    if role != "admin":
        bot.send_message(message.chat.id, "⛔ Нет доступа")
        return
    start_admin_step(message, "addadmin_id", "Введите ID нового админа:")

@bot.message_handler(commands=["deladmin"])
def deladmin_command(message):
    role = get_role(message.from_user.id)
    if role != "admin":
        bot.send_message(message.chat.id, "⛔ Нет доступа")
        return
    start_admin_step(message, "deladmin_id", "Введите ID админа для удаления:")

@bot.message_handler(commands=["logs"])
def logs_command(message):
    role = get_role(message.from_user.id)
    if role != "admin":
        bot.send_message(message.chat.id, "⛔ Нет доступа")
        return
    cursor.execute("SELECT actor, action, target, date FROM logs ORDER BY id DESC LIMIT 15")
    rows = cursor.fetchall()
    msg = "🧾 Логи:\n\n" + "\n".join([f"{r[3]} | {r[0]} | {r[1]} | {r[2]}" for r in rows])
    bot.send_message(message.chat.id, msg, reply_markup=get_main_keyboard("admin"))

# ---------- STEPS HANDLER ----------
@bot.message_handler(func=lambda m: m.from_user.id in user_states)
def steps_handler(message):
    if message.text == "Отмена":
        state = user_states[message.from_user.id]
        bot.send_message(message.chat.id, "❌ Действие отменено", reply_markup=get_main_keyboard(state.get("role")))
        del user_states[message.from_user.id]
        return

    state = user_states[message.from_user.id]
    role = state.get("role")

    # --- ADMIN ADD CARD ---
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
        return

    # --- OTHER ADMIN STEPS ---
    # Здесь обрабатываем все остальные пошаговые команды админа: check, history, setstatus, addadmin, deladmin
    # (аналогично шаблону выше — в каждом шаге проверяем state["step"], спрашиваем ID или ник и выполняем действие)

# ---------- RUN ----------
bot.infinity_polling()
