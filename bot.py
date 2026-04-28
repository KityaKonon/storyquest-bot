import os
import asyncio
import threading
from dotenv import load_dotenv
from openai import OpenAI
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
user_states = {}

web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "StoryQuest bot is running"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)


SYSTEM_PROMPT = """
Ты создаёшь интерактивный квест по книге или истории для ребёнка.

Правила:
- пиши на русском языке
- сцена должна быть короткой: 4-6 предложений
- сохраняй атмосферу исходного текста
- давай ровно 3 варианта выбора
- не пиши продолжение до выбора пользователя
- язык понятный детям 8-12 лет
- не используй страшные или жестокие подробности
"""

def choice_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1", callback_data="1")],
        [InlineKeyboardButton("2", callback_data="2")],
        [InlineKeyboardButton("3", callback_data="3")],
    ])

def generate_scene(user_id: int, source_text: str = "", choice: str | None = None) -> str:
    state = user_states.get(user_id, {})
    history = state.get("history", "")

    if choice:
        prompt = f"""
История квеста до этого момента:
{history}

Пользователь выбрал вариант: {choice}

Продолжи квест:
- покажи последствия выбора
- добавь новую проблему или поворот
- снова предложи ровно 3 варианта действий
"""
    else:
        prompt = f"""
Сделай первую сцену квеста по этому тексту:

{source_text}

Формат:
🎮 Название сцены

Текст сцены.

Что ты сделаешь?

1. ...
2. ...
3. ...
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    return response.output_text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 📚\n\n"
        "Я бот «Квест по книге».\n"
        "Пришли мне отрывок из книги или истории, "
        "а я превращу его в интерактивный квест с выбором действий."
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    source_text = update.message.text

    await update.message.reply_text("Создаю квест... ✨")

    scene = generate_scene(user_id=user_id, source_text=source_text)

    user_states[user_id] = {
        "source_text": source_text,
        "history": scene,
    }

    await update.message.reply_text(scene, reply_markup=choice_keyboard())

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    choice = query.data

    await query.message.reply_text("Продолжаю историю... ✨")

    scene = generate_scene(user_id=user_id, choice=choice)

    user_states[user_id]["history"] += f"\n\nВыбор пользователя: {choice}\n{scene}"

    await query.message.reply_text(scene, reply_markup=choice_keyboard())

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("Не найден TELEGRAM_BOT_TOKEN")
    if not OPENAI_API_KEY:
        raise ValueError("Не найден OPENAI_API_KEY")

    threading.Thread(target=run_web, daemon=True).start()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_choice))

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()