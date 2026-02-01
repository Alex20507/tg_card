import telebot
import sqlite3
from datetime import datetime
import os

# ----------- TOKEN -----------
TOKEN = os.getenv("TOKEN")
bot = telebot.TeleBot(TOKEN)

# ----------- ADMIN ID (для первого запуска) -----------
ADMIN_ID = 123456789  # Заменить своим Telegram ID

# ----------- DATABASE -----------
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

# Таблица пользователей с ником
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER UNIQUE,
    role TEXT,
    nickname TEXT
)
""")

# Таблица карточек
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

# Таблица истории статусов
cursor.execute("""
CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT,
    old_status TEXT,
    new_status TEXT,
    changed_by TEXT,
    date TEXT
)
""")

# Таблица логов с никами
cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT,
    action TEXT,
    target TEXT,
    date TEXT
)
""")

# Добавляем первого админа в таблицу
cursor.execute(
    "INSERT OR IGNORE INTO users (user_id, role, nickname) VALUES (?, 'admin', ?)",
    (ADMIN_ID, "MainAdmin")
)
conn.commit()

# ----------- HELPERS -----------
def log_action(user_id, action, target=""):
    cursor.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,))
    actor = cursor.fetchone()
    actor_nick = actor[0] if actor else "Неизвестно"
    
    cursor.execute(
        "INSERT INTO logs (actor, action, target, date) VALUES (?, ?, ?, ?)",
        (actor_nick, action, target, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
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
            bot.send_message(message.chat.id, "⛔ Нет доступа")
            return
        return func(message, role, *args, **kwargs)
    return wrapper

# ----------- COMMANDS -----------

# /start
@bot.message_handler(commands=["start"])
@access_required
def start(message, role):
    bot.send_message(
        message.chat.id,
        f"🗂 Card Database Bot\nРоль: {role}\n\n"
        "Админ:\n"
        "/addcard — добавить карточку\n"
        "/edit — редактировать карточку\n"
        "/check ID или НИК — поиск\n"
        "/history ID — история статусов\n"
        "/list — список карточек\n"
        "/addadmin ID НИК — добавить админа\n"
        "/logs — логи действий"
    )

# /addcard — добавление карточки одной строкой
@bot.message_handler(commands=["addcard"])
@access_required
def addcard(message, role):
    if role != "admin":
        return
    try:
        # Ожидаем: /addcard Имя Возраст ID ЧасовойПояс Ник Статус Комментарий
        parts = message.text.split(maxsplit=8)
        if len(parts) < 9:
            bot.send_message(message.chat.id, "⚠️ Формат неверный. Используйте:\n/addcard Имя Возраст ID ЧасовойПояс Ник Статус Комментарий")
            return
        _, name, age, uid, timezone, nickname, status, comment = parts[:8]
        
        cursor.execute("""
            INSERT INTO cards VALUES
            (NULL,?,?,?,?,?,?,?,?,?)
        """, (
            name,
            int(age),
            uid,
            timezone,
            nickname,
            status,
            comment,
            message.from_user.id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        log_action(message.from_user.id, "add_card", nickname)
        bot.send_message(message.chat.id, f"✅ Карточка {nickname} добавлена")
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

# /edit — редактирование карточки
@bot.message_handler(commands=["edit"])
@access_required
def edit_card(message, role):
    if role != "admin":
        return
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.send_message(message.chat.id, "⚠️ Используйте: /edit <UID>")
            return
        uid = parts[1]
        cursor.execute("SELECT * FROM cards WHERE uid = ?", (uid,))
        card = cursor.fetchone()
        if not card:
            bot.send_message(message.chat.id, "❌ Карточка не найдена")
            return
        
        # Отправляем текущую карточку
        text = (
            f"🗓 Текущая карточка {card[5]}:\n\n"
            f"Имя: {card[1]}\n"
            f"Возраст: {card[2]}\n"
            f"ID: {card[3]}\n"
            f"Часовой пояс: {card[4]}\n"
            f"Ник: {card[5]}\n"
            f"Статус: {card[6]}\n"
            f"Комментарий: {card[7]}"
        )
        bot.send_message(message.chat.id, text)
        bot.send_message(message.chat.id, "Введите новый статус и комментарий через | (например: active🟢 | Новый комментарий)")

        # Ожидаем следующее сообщение от того же пользователя
        @bot.message_handler(func=lambda m: m.from_user.id == message.from_user.id)
        def update_card(msg):
            try:
                status, comment = map(str.strip, msg.text.split("|", 1))
                cursor.execute("UPDATE cards SET status = ?, comment = ? WHERE uid = ?", (status, comment, uid))
                conn.commit()
                log_action(message.from_user.id, "edit_card", card[5])
                bot.send_message(msg.chat.id, f"✅ Карточка {card[5]} обновлена")
            except:
                bot.send_message(msg.chat.id, "⚠️ Неверный формат. Используйте: Статус | Комментарий")
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

# /check ID или Ник
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
        bot.send_message(message.chat.id, "❌ Ничего не найдено")
        return

    if len(rows) == 1:
        c = rows[0]
        cursor.execute("SELECT * FROM cards WHERE uid = ?", (c[0],))
        card = cursor.fetchone()
        text = (
            f"🗓 Описание карточки {card[5]}:\n\n"
            f"Имя: {card[1]}\nВозраст: {card[2]}\nID: {card[3]}\nЧасовой пояс: {card[4]}"
            f"\nНик: {card[5]}\nСтатус: {card[6]}\nКомментарий: {card[7]}"
        )
        bot.send_message(message.chat.id, text)
    else:
        msg = "🔍 Найдено несколько:\n\n"
        for r in rows:
            msg += f"{r[2]} | {r[0]} | {r[1]}\n"  # Ник | ID | Статус
        bot.send_message(message.chat.id, msg)

# /list — список карточек
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

# /addadmin — добавление админа
@bot.message_handler(commands=["addadmin"])
@access_required
def add_admin(message, role):
    if role != "admin":
        return
    try:
        _, tg_id, nickname = message.text.split(maxsplit=2)
        tg_id = int(tg_id)
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, role, nickname) VALUES (?, 'admin', ?)",
            (tg_id, nickname)
        )
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Админ {nickname} добавлен")
        log_action(message.from_user.id, "add_admin", nickname)
    except:
        bot.send_message(message.chat.id, "⚠️ Неверный формат. Используйте: /addadmin <id> <ник>")

# /logs — показать логи
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
        msg += f"{r[3]} | {r[0]} | {r[1]} | {r[2]}\n"
    bot.send_message(message.chat.id, msg)

# /history — история статусов
@bot.message_handler(commands=["history"])
@access_required
def history(message, role):
    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "⚠️ Используйте: /history <UID>")
        return
    uid = parts[1]
    cursor.execute("SELECT old_status, new_status, date FROM status_history WHERE uid = ?", (uid,))
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "📭 История пуста")
        return
    msg = "🔁 История статусов:\n\n"
    for r in rows:
        msg += f"{r[2]}: {r[0]} → {r[1]}\n"
    bot.send_message(message.chat.id, msg)

# ----------- RUN BOT -----------
bot.infinity_polling()
