import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

client = AsyncOpenAI(
    api_key=os.getenv("BOTHUB_API_KEY"),
    base_url="https://openai.bothub.chat/v1",
)

CONFIG_PATH = "horoscope_config.txt"
DEFAULT_MODEL = "gemini-3.1-flash-lite"


def load_config():
    """Читает модель и промпт из текстового файла при КАЖДОМ вызове."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        content = f.read()
    model = DEFAULT_MODEL
    prompt = content.strip()
    if "---PROMPT---" in content:
        head, prompt = content.split("---PROMPT---", 1)
        for line in head.splitlines():
            if line.lower().startswith("model:"):
                model = line.split(":", 1)[1].strip()
        prompt = prompt.strip()
    return model, prompt


def format_chart(natal):
    """Превращает сидерическую карту в читаемый список для модели."""
    chart = natal.get("карта_сидерик", {})
    asc = chart.get("асцендент", {})
    planets = chart.get("планеты", {})
    lines = []
    if asc:
        lines.append(f"Асцендент: {asc.get('знак')} {asc.get('градус')}°")
    for name, info in planets.items():
        lines.append(f"{name}: {info.get('знак')} {info.get('градус')}°")
    return "\n".join(lines)


async def generate_horoscope(name: str, natal: dict) -> str:
    model, system_prompt = load_config()
    chart_text = format_chart(natal)
    user_message = (
        f"Имя пользователя: {name or 'друг'}.\n"
        f"Знак Солнца по тропической (западной) системе: {natal.get('солнце_тропик', '')}.\n"
        f"Знак Солнца по сидерической (ведической) системе: {natal.get('солнце_сидерик', '')}.\n\n"
        f"ПОЛНАЯ НАТАЛЬНАЯ КАРТА (сидерическая, аянамша Лахири):\n"
        f"{chart_text}\n\n"
        f"Используй КОНКРЕТНЫЕ положения планет и асцендента из карты выше для "
        f"обоснования КАЖДОГО вывода. В разных блоках опирайся на разные планеты. "
        f"Составь гороскоп строго по инструкции."
    )
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.9,
    )
    return response.choices[0].message.content
