from tarot import generate_horoscope
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
from zoneinfo import ZoneInfo
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
import swisseph as swe

import models
from database import engine, SessionLocal, Base

# Создаём таблицы в базе при запуске (если их ещё нет)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Астрель API")

# На время разработки разрешаем запросы отовсюду.
# Перед публичным запуском сузить до своего домена.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Подключение к базе на время запроса ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Астрологическая часть ---
SIGNS = ["Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
         "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы"]

PLANETS = {
    "Солнце": swe.SUN, "Луна": swe.MOON, "Меркурий": swe.MERCURY,
    "Венера": swe.VENUS, "Марс": swe.MARS, "Юпитер": swe.JUPITER,
    "Сатурн": swe.SATURN, "Уран": swe.URANUS, "Нептун": swe.NEPTUNE,
    "Плутон": swe.PLUTO,
}

geolocator = Nominatim(user_agent="astrel-app")
tf = TimezoneFinder()


def deg_to_sign(deg):
    """Градус на круге (0-360) -> знак зодиака и градус внутри знака."""
    deg = deg % 360
    index = int(deg // 30)
    return SIGNS[index], round(deg % 30, 2)


def compute_natal(date: str, time: str, place: str, zodiac: str = "tropical"):
    """Главная функция расчёта натальной карты."""
    # 1) Город -> координаты
    location = geolocator.geocode(place)
    if location is None:
        raise HTTPException(status_code=404, detail=f"Не нашёл место: {place}")
    lat, lon = location.latitude, location.longitude

    # 2) Координаты -> часовой пояс
    tzname = tf.timezone_at(lat=lat, lng=lon)
    if tzname is None:
        raise HTTPException(status_code=404, detail="Не определил часовой пояс")

    # 3) Дата и время
    year, month, day = map(int, date.split("-"))
    hour, minute = map(int, time.split(":"))

    # zoneinfo сам учтёт историческое летнее время
    dt = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(tzname))
    tz_offset = dt.utcoffset().total_seconds() / 3600

    ut_decimal = hour + minute / 60 - tz_offset
    jd = swe.julday(year, month, day, ut_decimal)

    # MOSEPH = встроенный режим, не требует файлов эфемерид
    flag = swe.FLG_MOSEPH | swe.FLG_SPEED
    if zodiac == "sidereal":
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
        flag |= swe.FLG_SIDEREAL

    planets = {}
    for name, code in PLANETS.items():
        pos, _ = swe.calc_ut(jd, code, flag)
        sign, d = deg_to_sign(pos[0])
        planets[name] = {"знак": sign, "градус": d}

    # Дома и асцендент (b'P' = система Плацидуса)
    if zodiac == "sidereal":
        cusps, ascmc = swe.houses_ex(jd, lat, lon, b'P', swe.FLG_SIDEREAL)
    else:
        cusps, ascmc = swe.houses(jd, lat, lon, b'P')
    asc_sign, asc_deg = deg_to_sign(ascmc[0])

    # --- Оба знака Солнца (для гороскопа) ---
    # Тропический (без флага сидерики)
    sun_trop, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_MOSEPH)
    sun_trop_sign, _ = deg_to_sign(sun_trop[0])
    # Сидерический (Лахири)
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    sun_sid, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_MOSEPH | swe.FLG_SIDEREAL)
    sun_sid_sign, _ = deg_to_sign(sun_sid[0])

    return {
        "место": location.address,
        "часовой_пояс": tzname,
        "зодиак": zodiac,
        "асцендент": {"знак": asc_sign, "градус": asc_deg},
        "планеты": planets,
        "солнце_тропик": sun_trop_sign,
        "солнце_сидерик": sun_sid_sign,
    }


# --- Схемы входных данных ---
class PersonIn(BaseModel):
    name: str
    birth_date: str
    birth_time: str
    birth_place: str
    vk_id: str | None = None


class RelativeIn(BaseModel):
    name: str
    birth_date: str
    birth_time: str
    birth_place: str
    relation_type: str


# --- Маршруты ---
@app.get("/")
def index():
    """Главная страница — форма (index.html)."""
    return FileResponse("index.html")


@app.get("/health")
def health():
    return {"message": "Астрель бэкенд жив!"}


@app.get("/natal")
def natal_direct(date: str, time: str, place: str, zodiac: str = "tropical"):
    """Прямой расчёт карты по введённым данным (для формы)."""
    return compute_natal(date, time, place, zodiac)


@app.post("/users")
def create_user(person: PersonIn, db: Session = Depends(get_db)):
    user = models.User(**person.dict())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).all()


@app.get("/users/{user_id}/natal")
def user_natal(user_id: int, zodiac: str = "tropical", db: Session = Depends(get_db)):
    user = db.query(models.User).get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return compute_natal(user.birth_date, user.birth_time, user.birth_place, zodiac)


@app.post("/users/{user_id}/relatives")
def add_relative(user_id: int, rel: RelativeIn, db: Session = Depends(get_db)):
    user = db.query(models.User).get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    relative = models.Relative(owner_id=user_id, **rel.dict())
    db.add(relative)
    db.commit()
    db.refresh(relative)
    return relative


@app.get("/users/{user_id}/relatives")
def list_relatives(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.Relative).filter(models.Relative.owner_id == user_id).all()


@app.get("/relatives/{relative_id}/natal")
def relative_natal(relative_id: int, zodiac: str = "tropical", db: Session = Depends(get_db)):
    rel = db.query(models.Relative).get(relative_id)
    if rel is None:
        raise HTTPException(status_code=404, detail="Не найдено")
    return compute_natal(rel.birth_date, rel.birth_time, rel.birth_place, zodiac)


@app.get("/horoscope")
async def horoscope(tropical_sign: str, sidereal_sign: str, name: str = ""):
    """Гороскоп-прогноз через нейросеть на основе имени и двух знаков Солнца."""
    if not tropical_sign or not sidereal_sign:
        return {"error": "Не указаны знаки зодиака"}
    text = await generate_horoscope(name, tropical_sign, sidereal_sign)
    return {"horoscope": text}
