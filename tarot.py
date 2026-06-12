import random
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Загружаем ключи из файла .env
load_dotenv()

# Инициализируем клиента BotHub
client = AsyncOpenAI(
    api_key=os.getenv("BOTHUB_API_KEY"),
    base_url="https://openai.bothub.chat/v1",
)

# 22 Старших Аркана
MAJOR_ARCANA = [
    "Шут", "Маг", "Верховная Жрица", "Императрица", "Император", "Иерофант", "Влюбленные",
    "Колесница", "Сила", "Отшельник", "Колесо Фортуны", "Справедливость",
    "Повешенный", "Смерть", "Умеренность", "Дьявол", "Башня", "Звезда",
    "Луна", "Солнце", "Суд", "Мир"
]

async def get_tarot_reading(sun_sign: str):
    # Тянем 3 уникальные карты
    drawn_cards = random.sample(MAJOR_ARCANA, 3)
    cards_text = f"1. Прошлое: {drawn_cards[0]}, 2. Настоящее: {drawn_cards[1]}, 3. Будущее: {drawn_cards[2]}"

    prompt = f"""
    Сделай короткий расклад Таро для человека, чей знак зодиака (Солнце) - {sun_sign}.
    Выпали карты (только Старшие Арканы):
    {cards_text}

    Напиши трактовку в позитивном и поддерживающем ключе.
    Объясни, как эти карты резонируют с энергией знака {sun_sign}.
    Ответ должен быть в формате HTML (используй теги <p>, <b>, <br>, но без тегов <html> и <body>).
    """

    try:
        response = await client.chat.completions.create(
            model="gemini-3.1-flash-lite",
            messages=[
                {"role": "system", "content": "Ты опытный, добрый астролог и таролог."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        reading = response.choices[0].message.content
        return {"cards": drawn_cards, "reading": reading}
    except Exception as e:
        return {"error": f"Ошибка при обращении к нейросети: {str(e)}"}
