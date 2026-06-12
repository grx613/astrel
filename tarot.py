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
    """Читает модель и системный промпт из текстового файла.
    Файл читается при КАЖДОМ вызове — правки применяются без перезапуска."""
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


async def generate_horoscope(name: str, tropical_sign: str, sidereal_sign: str) -> str:
    model, system_prompt = load_config()
    user_message = (
        f"Имя пользователя: {name or 'друг'}.\n"
        f"Знак Солнца по тропической (западной) системе: {tropical_sign}.\n"
        f"Знак Солнца по сидерической (ведической) системе: {sidereal_sign}.\n"
        f"Составь гороскоп строго по инструкции и обязательно обратись к пользователю по имени."
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
