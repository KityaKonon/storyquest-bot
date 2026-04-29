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

MAX_STEPS = 7

SYSTEM_PROMPT = """
Ты создаёшь интерактивный квест по книге или истории для ребёнка.

Главные правила:
- пиши на русском языке
- язык понятный детям 8-12 лет
- сцена должна быть короткой: 4-6 предложений
- всегда давай ровно 3 варианта выбора
- не используй страшные или жестокие подробности
- не пиши длинный пересказ книги
- сохраняй атмосферу исходной истории

Очень важно:
- если квест по отрывку, опирайся только на героев, место, конфликт и события из присланного текста
- не добавляй случайных новых персонажей и локации
- если квест по названию книги, держись известных героев, мира и основного сюжета этой книги
- если выбор пользователя уводит слишком далеко от сюжета, мягко возвращай его обратно
"""

def main_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📄 Квест по моему отрывку", "callback_data": "mode_excerpt"}],
            [{"text": "📚 Квест по названию книги", "callback_data": "mode_book"}],
        ]
    }

def choice_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "1", "callback_data": "choice_1"}],
            [{"text": "2", "callback_data": "choice_2"}],
            [{"text": "3", "callback_data": "choice_3"}],
        ]
    }

def new_quest_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🔁 Начать новый квест", "callback_data": "new_quest"}],
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

def ask_openai(prompt):
    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content

def build_book_context(book_title):
    prompt = f"""
Пользователь хочет создать детский квест по названию книги:

"{book_title}"

Задача:
1. Определи, существует ли такая известная книга.
2. Если книга неизвестна, выведи строго:
NOT_FOUND
3. Если книга известна, кратко опиши опорный контекст для квеста:
- название книги
- главные герои
- место действия
- центральный конфликт
- атмосфера
- какие события допустимы в рамках сюжета

Не пересказывай книгу подробно.
Не цитируй текст книги.
"""

    result = ask_openai(prompt).strip()
    return result

def generate_scene(user_id, source_text="", choice=None):
    try:
        print("=== GENERATE START ===", flush=True)
        print("USER:", user_id, flush=True)
        print("SOURCE TEXT:", source_text, flush=True)
        print("CHOICE:", choice, flush=True)

        state = user_states.get(user_id, {})
        history = state.get("history", "")
        source_type = state.get("source_type", "")
        source_context = state.get("source_context", "")
        step = state.get("step", 1)

        if source_type == "excerpt":
            base_rule = f"""
Источник квеста — отрывок пользователя.

Исходный текст:
{source_context}

Правило:
держись только героев, места, конфликта и атмосферы этого отрывка.
Не добавляй случайных новых персонажей и локации.
"""
        elif source_type == "book":
            base_rule = f"""
Источник квеста — известная книга.

Опорный контекст книги:
{source_context}

Правило:
держись героев, мира, атмосферы и основного сюжета этой книги.
Не добавляй случайных новых персонажей и события, которые не подходят этой книге.
"""
        else:
            base_rule = f"""
Источник квеста:
{source_text}
"""

        if choice:
            prompt = f"""
{base_rule}

История квеста до этого момента:
{history}

Это шаг {step} из {MAX_STEPS}.

Пользователь выбрал вариант: {choice}

Продолжи квест:
- покажи последствия выбора
- добавь небольшое развитие сюжета
- не уходи от исходной истории
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
{base_rule}

Создай первую сцену квеста.
Это шаг 1 из {MAX_STEPS}.

Формат:
🎮 Название сцены

Текст сцены.

Что ты сделаешь?

1. ...
2. ...
3. ...
"""

        print("OPENAI REQUEST START", flush=True)
        result = ask_openai(prompt)
        print("OPENAI RESULT:", result, flush=True)

        return result

    except Exception as e:
        error_text = str(e)
        print("ERROR IN GENERATE:", error_text, flush=True)
        return f"Ошибка при обращении к OpenAI:\n{error_text}"

def generate_final(user_id):
    try:
        state = user_states.get(user_id, {})
        history = state.get("history", "")
        source_context = state.get("source_context", "")
        source_type = state.get("source_type", "")

        prompt = f"""
Заверши детский квест.

Тип источника: {source_type}

Источник:
{source_context}

История квеста:
{history}

Сделай короткий финал:
- 4-6 предложений
- добрый и завершённый
- без новых случайных персонажей
- с ощущением, что ребёнок справился

Обязательно начни финал фразой:
🎉 Ты справился!
"""

        result = ask_openai(prompt)
        return result

    except Exception as e:
        error_text = str(e)
        print("ERROR IN FINAL:", error_text, flush=True)
        return f"🎉 Ты справился!\n\nКвест завершён."

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
            text = message.get("text", "").strip()

            print("MESSAGE TEXT:", text, flush=True)

            if text == "/start":
                user_states[user_id] = {"mode": None}
                send_message(
                    chat_id,
                    "Привет! 📚\n\n"
                    "Я бот «Квест по книге».\n"
                    "Я могу сделать интерактивный квест по твоему отрывку или по названию известной книги.\n\n"
                    "Выбери режим:",
                    reply_markup=main_menu_keyboard()
                )
                return "ok"

            state = user_states.get(user_id, {})

            if state.get("mode") == "waiting_excerpt":
                send_message(chat_id, "Создаю квест по твоему отрывку... ✨")

                user_states[user_id] = {
                    "mode": "quest",
                    "source_type": "excerpt",
                    "source_context": text,
                    "source_text": text,
                    "history": "",
                    "step": 1,
                }

                scene = generate_scene(user_id=user_id, source_text=text)

                if scene.startswith("Ошибка при обращении к OpenAI:"):
                    send_message(chat_id, scene)
                    return "ok"

                user_states[user_id]["history"] = scene

                send_message(chat_id, scene, reply_markup=choice_keyboard())
                return "ok"

            if state.get("mode") == "waiting_book":
                send_message(chat_id, "Ищу книгу и готовлю сюжетную рамку... 📚")

                book_context = build_book_context(text)

                if book_context == "NOT_FOUND" or book_context.startswith("NOT_FOUND"):
                    send_message(
                        chat_id,
                        "К сожалению, я не нашёл такую книгу. "
                        "Попробуй другое название или выбери режим «Квест по моему отрывку».",
                        reply_markup=main_menu_keyboard()
                    )
                    user_states[user_id] = {"mode": None}
                    return "ok"

                user_states[user_id] = {
                    "mode": "quest",
                    "source_type": "book",
                    "source_context": book_context,
                    "source_text": text,
                    "history": "",
                    "step": 1,
                }

                send_message(chat_id, "Создаю квест по книге... ✨")

                scene = generate_scene(user_id=user_id, source_text=text)

                if scene.startswith("Ошибка при обращении к OpenAI:"):
                    send_message(chat_id, scene)
                    return "ok"

                user_states[user_id]["history"] = scene

                send_message(chat_id, scene, reply_markup=choice_keyboard())
                return "ok"

            send_message(
                chat_id,
                "Сначала выбери режим квеста:",
                reply_markup=main_menu_keyboard()
            )

        elif "callback_query" in update:
            callback = update["callback_query"]
            callback_id = callback["id"]
            chat_id = callback["message"]["chat"]["id"]
            user_id = callback["from"]["id"]
            data = callback["data"]

            print("CALLBACK DATA:", data, flush=True)

            answer_callback(callback_id)

            if data == "new_quest":
                user_states[user_id] = {"mode": None}
                send_message(
                    chat_id,
                    "Начинаем новый квест! 📚\n\nВыбери режим:",
                    reply_markup=main_menu_keyboard()
                )
                return "ok"

            if data == "mode_excerpt":
                user_states[user_id] = {"mode": "waiting_excerpt"}
                send_message(
                    chat_id,
                    "Пришли отрывок истории или книги.\n\n"
                    "Я сделаю квест по героям, месту и событиям этого текста."
                )
                return "ok"

            if data == "mode_book":
                user_states[user_id] = {"mode": "waiting_book"}
                send_message(
                    chat_id,
                    "Напиши название книги.\n\n"
                    "Например: «Питер Пэн», «Алиса в Стране чудес», «Маленький принц»."
                )
                return "ok"

            if data.startswith("choice_"):
                choice = data.replace("choice_", "")

                state = user_states.get(user_id)

                if not state or state.get("mode") != "quest":
                    send_message(
                        chat_id,
                        "Квест не найден. Начни новый квест.",
                        reply_markup=new_quest_keyboard()
                    )
                    return "ok"

                current_step = state.get("step", 1)

                if current_step >= MAX_STEPS:
                    final_text = generate_final(user_id)
                    send_message(chat_id, final_text, reply_markup=new_quest_keyboard())
                    user_states[user_id] = {"mode": None}
                    return "ok"

                send_message(chat_id, "Продолжаю историю... ✨")

                next_step = current_step + 1
                user_states[user_id]["step"] = next_step

                scene = generate_scene(user_id=user_id, choice=choice)

                if scene.startswith("Ошибка при обращении к OpenAI:"):
                    send_message(chat_id, scene)
                    return "ok"

                user_states[user_id]["history"] += f"\n\nВыбор пользователя: {choice}\n{scene}"

                if next_step >= MAX_STEPS:
                    final_text = generate_final(user_id)
                    send_message(chat_id, final_text, reply_markup=new_quest_keyboard())
                    user_states[user_id] = {"mode": None}
                else:
                    send_message(chat_id, scene, reply_markup=choice_keyboard())

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