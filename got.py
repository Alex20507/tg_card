import os
import json
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = {123456789}  # ← замени на свой ID

DATA_FILE = "cards.json"

# ===== Хранилище =====
def load_cards():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_cards(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ===== Состояния =====
USER_ID, USER_NAME, USER_PHONE = range(3)
ADMIN_ADD = 10

# ===== Старт =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in ADMIN_IDS:
        text = "здорово, а теперь запомни вокруг тебя админы, бот и долбаебы которые стопудово заполнят неправильно описание"
    else:
        text = "здорово, мозг админам не ебите правильно заполните все по братски)"

    keyboard = [["➕ Добавить карточку"]]
    await update.message.reply_text(text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# ===== Пользователь: добавить карточку =====
async def add_card_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введи ID:")
    return USER_ID

async def user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["id"] = update.message.text
    await update.message.reply_text("Имя:")
    return USER_NAME

async def user_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("Телефон:")
    return USER_PHONE

async def user_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text

    cards = load_cards()
    cid = context.user_data["id"]

    cards[cid] = {
        "name": context.user_data["name"],
        "phone": context.user_data["phone"],
        "status": "new",
        "comment": ""
    }

    save_cards(cards)

    await update.message.reply_text("✅ Карточка добавлена")
    return ConversationHandler.END

# ===== Админ: список =====
async def list_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("❌ Нет доступа")

    cards = load_cards()
    if not cards:
        return await update.message.reply_text("Пусто")

    text = "\n".join([f"{cid}: {data['name']} ({data['status']})" for cid, data in cards.items()])
    await update.message.reply_text(text)

# ===== Проверка =====
async def check_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("❌ Нет доступа")

    if not context.args:
        return await update.message.reply_text("Используй: /check ID")

    cid = context.args[0]
    cards = load_cards()

    if cid not in cards:
        return await update.message.reply_text("Не найдено")

    c = cards[cid]
    text = f"""
ID: {cid}
Имя: {c['name']}
Телефон: {c['phone']}
Статус: {c['status']}
Комментарий: {c['comment']}
"""
    await update.message.reply_text(text)

# ===== Статус =====
async def set_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("❌ Нет доступа")

    if len(context.args) < 2:
        return await update.message.reply_text("Используй: /setstatus ID статус")

    cid, status = context.args[0], context.args[1]
    cards = load_cards()

    if cid not in cards:
        return await update.message.reply_text("Не найдено")

    cards[cid]["status"] = status
    save_cards(cards)

    await update.message.reply_text("✅ Статус обновлён")

# ===== Админы =====
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    new_admin = int(context.args[0])
    ADMIN_IDS.add(new_admin)
    await update.message.reply_text("👑 Админ добавлен")

async def del_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    admin_id = int(context.args[0])
    ADMIN_IDS.discard(admin_id)
    await update.message.reply_text("🗑 Админ удалён")

# ===== Логи =====
async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("❌ Нет доступа")
    await update.message.reply_text("Логи пока не реализованы 😎")

# ===== Отмена =====
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено")
    return ConversationHandler.END

# ===== Запуск =====
def main():
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("➕ Добавить карточку"), add_card_start),
            CommandHandler("add", add_card_start),
        ],
        states={
            USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_id)],
            USER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_name)],
            USER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CommandHandler("list", list_cards))
    app.add_handler(CommandHandler("check", check_card))
    app.add_handler(CommandHandler("setstatus", set_status))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("deladmin", del_admin))
    app.add_handler(CommandHandler("logs", logs))

    print("BOT STARTED")
    app.run_polling()

if __name__ == "__main__":
    main()
