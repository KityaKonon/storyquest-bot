import os
import requests
from flask import Flask, request
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://storyquest-bot.onrender.com")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
client = OpenAI(api_key=OPENAI_API_KEY)

app = Flask(__name__)
user_states = {}

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

def keyboard():
    return {
        "inline_keyboard": [
            [{"text": "1", "callback_data": "1"}],
            [{"text": "2", "callback_data": "2"}],
            [{"text": "3", "callback_data": "3"}],
        ]
    }

def send_message(chat_id, text, reply_markup=None):
    data = {
        "chat_id": chat_id,
        "text": text,
    }
    if reply_markup:
        data["reply_markup"] = reply_markup

    requests.post(f"{TELEGRAM_API}/sendMessage", json=data, timeout=20)

def answer_callback(callback_query_id):
    requests.post(
        f"{TELEGRAM_API}/answerCallbackQuery",
        json={"callback_query_id": callback_query_id},
        timeout=20
    )

def generate_scene(user_id, source_text="", choice=None):
    history = user_states.get(user_id, {}).get("history", "")

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

@app.route("/")
def home():
    return "StoryQuest bot is running"

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()

    try:
        if "message" in update:
            message = update["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            text = message.get("text", "")

            if text == "/start":
                send_message(
                    chat_id,
                    "Привет! 📚\n\nЯ бот «Квест по книге».\n"
                    "Пришли мне отрывок из книги или истории, "
                    "а я превращу его в интерактивный квест с выбором действий."
                )
                return "ok"

            send_message(chat_id, "Создаю квест... ✨")

            scene = generate_scene(user_id=user_id, source_text=text)

            user_states[user_id] = {
                "source_text": text,
                "history": scene,
            }

            send_message(chat_id, scene, reply_markup=keyboard())

        elif "callback_query" in update:
            callback = update["callback_query"]
            callback_id = callback["id"]
            chat_id = callback["message"]["chat"]["id"]
            user_id = callback["from"]["id"]
            choice = callback["data"]

            answer_callback(callback_id)
            send_message(chat_id, "Продолжаю историю... ✨")

            scene = generate_scene(user_id=user_id, choice=choice)

            if user_id not in user_states:
                user_states[user_id] = {"history": ""}

            user_states[user_id]["history"] += f"\n\nВыбор пользователя: {choice}\n{scene}"

            send_message(chat_id, scene, reply_markup=keyboard())

    except Exception as e:
        print("ERROR:", e, flush=True)
        if "message" in update:
            chat_id = update["message"]["chat"]["id"]
            send_message(chat_id, "Произошла ошибка при создании квеста. Попробуй ещё раз чуть позже.")

    return "ok"

def set_webhook():
    url = f"{WEBHOOK_URL}/webhook"
    response = requests.post(
        f"{TELEGRAM_API}/setWebhook",
        json={
            "url": url,
            "drop_pending_updates": True
        },
        timeout=20
    )
    print("Webhook set:", response.text, flush=True)

if __name__ == "__main__":
    if not TELEGRAM_TOKEN:
        raise ValueError("Не найден TELEGRAM_BOT_TOKEN")
    if not OPENAI_API_KEY:
        raise ValueError("Не найден OPENAI_API_KEY")

    set_webhook()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)