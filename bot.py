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

    response = requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json=data,
        timeout=20
    )

    print("SEND MESSAGE RESPONSE:", response.text, flush=True)

def answer_callback(callback_query_id):
    response = requests.post(
        f"{TELEGRAM_API}/answerCallbackQuery",
        json={"callback_query_id": callback_query_id},
        timeout=20
    )

    print("ANSWER CALLBACK RESPONSE:", response.text, flush=True)

def generate_scene(user_id, source_text="", choice=None):
    try:
        print("=== GENERATE START ===", flush=True)
        print("USER:", user_id, flush=True)
        print("SOURCE TEXT:", source_text, flush=True)
        print("CHOICE:", choice, flush=True)

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

Формат:
🎮 Название сцены

Текст сцены.

Что ты сделаешь?

1. ...
2. ...
3. ...
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

        print("OPENAI REQUEST START", flush=True)

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

        print("OPENAI REQUEST DONE", flush=True)

        result = response.output_text

        print("OPENAI RESULT:", result, flush=True)

        return result

    except Exception as e:
        error_text = str(e)
        print("ERROR IN GENERATE:", error_text, flush=True)
        return f"Ошибка при обращении к OpenAI:\n{error_text}"

@app.route("/")
def home():
    return "StoryQuest bot is running"

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()

    print("WEBHOOK UPDATE:", update, flush=True)

    try:
        if "message" in update:
            message = update["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            text = message.get("text", "")

            print("MESSAGE TEXT:", text, flush=True)

            if text == "/start":
                send_message(
                    chat_id,
                    "Привет! 📚\n\n"
                    "Я бот «Квест по книге».\n"
                    "Пришли мне отрывок из книги или истории, "
                    "а я превращу его в интерактивный квест с выбором действий."
                )
                return "ok"

            send_message(chat_id, "Создаю квест... ✨")

            scene = generate_scene(user_id=user_id, source_text=text)

            if scene.startswith("Ошибка при обращении к OpenAI:"):
                send_message(chat_id, scene)
                return "ok"

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

            print("CALLBACK CHOICE:", choice, flush=True)

            answer_callback(callback_id)

            send_message(chat_id, "Продолжаю историю... ✨")

            scene = generate_scene(user_id=user_id, choice=choice)

            if scene.startswith("Ошибка при обращении к OpenAI:"):
                send_message(chat_id, scene)
                return "ok"

            if user_id not in user_states:
                user_states[user_id] = {
                    "source_text": "",
                    "history": ""
                }

            user_states[user_id]["history"] += f"\n\nВыбор пользователя: {choice}\n{scene}"

            send_message(chat_id, scene, reply_markup=keyboard())

    except Exception as e:
        error_text = str(e)
        print("ERROR IN WEBHOOK:", error_text, flush=True)

        try:
            if "message" in update:
                chat_id = update["message"]["chat"]["id"]
            elif "callback_query" in update:
                chat_id = update["callback_query"]["message"]["chat"]["id"]
            else:
                chat_id = None

            if chat_id:
                send_message(
                    chat_id,
                    f"Произошла ошибка в обработке сообщения:\n{error_text}"
                )
        except Exception as send_error:
            print("ERROR WHILE SENDING ERROR MESSAGE:", str(send_error), flush=True)

    return "ok"

def set_webhook():
    url = f"{WEBHOOK_URL}/webhook"

    print("SETTING WEBHOOK TO:", url, flush=True)

    response = requests.post(
        f"{TELEGRAM_API}/setWebhook",
        json={
            "url": url,
            "drop_pending_updates": True
        },
        timeout=20
    )

    print("WEBHOOK SET RESPONSE:", response.text, flush=True)

if __name__ == "__main__":
    if not TELEGRAM_TOKEN:
        raise ValueError("Не найден TELEGRAM_BOT_TOKEN")

    if not OPENAI_API_KEY:
        raise ValueError("Не найден OPENAI_API_KEY")

    set_webhook()

    port = int(os.environ.get("PORT", 10000))

    print("STARTING FLASK APP ON PORT:", port, flush=True)

    app.run(host="0.0.0.0", port=port)