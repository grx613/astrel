import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

client = AsyncOpenAI(
    api_key=os.getenv("BOTHUB_API_KEY"),
    base_url="https://openai.bothub.chat/v1",
)

CONFIG_PATH = "horoscope_config.txt"
SYNASTRY_CONFIG_PATH = "synastry_config.txt"
DEFAULT_MODEL = "gemini-3.1-flash-lite"

# --- Достоинства планет (классические 7 планет) ---
ОБИТЕЛЬ = {
    "Солнце": ["Лев"], "Луна": ["Рак"], "Меркурий": ["Близнецы", "Дева"],
    "Венера": ["Телец", "Весы"], "Марс": ["Овен", "Скорпион"],
    "Юпитер": ["Стрелец", "Рыбы"], "Сатурн": ["Козерог", "Водолей"],
}
ЭКЗАЛЬТАЦИЯ = {
    "Солнце": "Овен", "Луна": "Телец", "Меркурий": "Дева",
    "Венера": "Рыбы", "Марс": "Козерог", "Юпитер": "Рак", "Сатурн": "Весы",
}
ПАДЕНИЕ = {
    "Солнце": "Весы", "Луна": "Скорпион", "Меркурий": "Рыбы",
    "Венера": "Дева", "Марс": "Рак", "Юпитер": "Козерог", "Сатурн": "Овен",
}
ИЗГНАНИЕ = {
    "Солнце": ["Водолей"], "Луна": ["Козерог"], "Меркурий": ["Стрелец", "Рыбы"],
    "Венера": ["Овен", "Скорпион"], "Марс": ["Телец", "Весы"],
    "Юпитер": ["Близнецы", "Дева"], "Сатурн": ["Рак", "Лев"],
}

def dignity(planet, sign):
    if ЭКЗАЛЬТАЦИЯ.get(planet) == sign: return "в ЭКЗАЛЬТАЦИИ (на пике силы, ярко проявлена)"
    if sign in ОБИТЕЛЬ.get(planet, []): return "в ОБИТЕЛИ (управляет знаком, сильная и уверенная)"
    if ПАДЕНИЕ.get(planet) == sign: return "в ПАДЕНИИ (ослаблена, даётся тяжело)"
    if sign in ИЗГНАНИЕ.get(planet, []): return "в ИЗГНАНИИ (в напряжении, некомфортно)"
    return ""

def _read_config(path):
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return DEFAULT_MODEL, "Ты астролог."
    model = DEFAULT_MODEL
    prompt = content.strip()
    if "---PROMPT---" in content:
        head, prompt = content.split("---PROMPT---", 1)
        for line in head.splitlines():
            if line.lower().startswith("model:"):
                model = line.split(":", 1)[1].strip()
        prompt = prompt.strip()
    return model, prompt

def load_config(): return _read_config(CONFIG_PATH)
def load_synastry_config(): return _read_config(SYNASTRY_CONFIG_PATH)

def format_chart(natal):
    chart = natal.get("карта_сидерик", {})
    asc = chart.get("асцендент", {})
    planets = chart.get("планеты", {})
    lines = []
    if asc: lines.append(f"Асцендент: {asc.get('знак')} {asc.get('градус')}°")
    for name, info in planets.items():
        sign = info.get("знак")
        d = dignity(name, sign)
        suffix = f" — {d}" if d else ""
        lines.append(f"{name}: {sign} {info.get('градус')}°{suffix}")
    return "\n".join(lines)

async def generate_horoscope(name: str, natal: dict) -> str:
    model, system_prompt = load_config()
    chart_text = format_chart(natal)
    user_message = (
        f"Имя пользователя: {name or 'друг'}.\n"
        f"Знак Солнца (тропик): {natal.get('солнце_тропик', '')}.\n"
        f"Знак Солнца (сидерик): {natal.get('солнце_сидерик', '')}.\n\n"
        f"ПОЛНАЯ НАТАЛЬНАЯ КАРТА:\n{chart_text}\n\n"
        f"Опирайся на карту. Обыграй достоинства планет."
    )
    response = await client.chat.completions.create(
        model=model, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
        temperature=0.9,
    )
    return response.choices[0].message.content

def format_scores(scores):
    if not scores:
        return ""
    lines = ["РАСЧЁТ АСПЕКТОВ (опирайся на эти цифры, обязательно упомяни ключевые аспекты и углы в тексте):"]
    for c in scores.get("criteria", []):
        det = "; ".join(c.get("details", [])) or "явных аспектов нет"
        lines.append("- %s %s: %d%% (%s)" % (c.get("emoji", ""), c.get("name", ""), c.get("score", 0), det))
    lines.append("ОБЩАЯ СОВМЕСТИМОСТЬ: %d%% — %s" % (scores.get("overall", 0), scores.get("label", "")))
    return "\n".join(lines) + "\n\n"


async def generate_synastry(name1: str, natal1: dict, name2: str, natal2: dict, scores: dict = None) -> str:
    model, system_prompt = load_synastry_config()
    chart1 = format_chart(natal1)
    chart2 = format_chart(natal2)
    user_message = (
        f"ПАРТНЁР 1: {name1 or 'Первый партнёр'}\n"
        f"Солнце (тропик): {natal1.get('солнце_тропик', '')}\n"
        f"Карта:\n{chart1}\n\n"
        f"ПАРТНЁР 2: {name2 or 'Второй партнёр'}\n"
        f"Солнце (тропик): {natal2.get('солнце_тропик', '')}\n"
        f"Карта:\n{chart2}\n\n"
        f"{format_scores(scores)}"
        f"Сравни эти две карты и составь анализ совместимости (синастрию) по инструкции."
    )
    response = await client.chat.completions.create(
        model=model, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
        temperature=0.9,
    )
    return response.choices[0].message.content
