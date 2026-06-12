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

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Астрель API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
    deg = deg % 360
    index = int(deg // 30)
    return SIGNS[index], round(deg % 30, 2)


def compute_natal(date: str, time: str, place: str, zodiac: str = "tropical"):
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
    dt = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(tzname))
    tz_offset = dt.utcoffset().total_seconds() / 3600
    ut_decimal = hour + minute / 60 - tz_offset
    jd = swe.julday(year, month, day, ut_decimal)

    # --- Карта для отображения (в выбранной системе) ---
    flag = swe.FLG_MOSEPH | swe.FLG_SPEED
    if zodiac == "sidereal":
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
        flag |= swe.FLG_SIDEREAL

    planets = {}
    for name, code in PLANETS.items():
        pos, _ = swe.calc_ut(jd, code, flag)
        sign, d = deg_to_sign(pos[0])
        planets[name] = {"знак": sign, "градус": d}

    if zodiac == "sidereal":
        cusps, ascmc = swe.houses_ex(jd, lat, lon, b'P', swe.FLG_SIDEREAL)
    else:
        cusps, ascmc = swe.houses(jd, lat, lon, b'P')
    asc_sign, asc_deg = deg_to_sign(ascmc[0])

    # --- Полная СИДЕРИЧЕСКАЯ карта (всегда, для гороскопа) ---
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    sid_flag = swe.FLG_MOSEPH | swe.FLG_SPEED | swe.FLG_SIDEREAL
    sid_planets = {}
    for name, code in PLANETS.items():
        pos, _ = swe.calc_ut(jd, code, sid_flag)
        s, d = deg_to_sign(pos[0])
        sid_planets[name] = {"знак": s, "градус": d}
    sid_cusps, sid_ascmc = swe.houses_ex(jd, lat, lon, b'P', swe.FLG_SIDEREAL)
    sid_asc_sign, sid_asc_deg = deg_to_sign(sid_ascmc[0])

    # --- Тропический знак Солнца (для вступления гороскопа) ---
    sun_trop, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_MOSEPH)
    sun_trop_sign, _ = deg_to_sign(sun_trop[0])

    return {
        "место": location.address,
        "часовой_пояс": tzname,
        "зодиак": zodiac,
        "асцендент": {"знак": asc_sign, "градус": asc_deg},
        "планеты": planets,
        "солнце_тропик": sun_trop_sign,
        "солнце_сидерик": sid_planets["Солнце"]["знак"],
        "карта_сидерик": {
            "асцендент": {"знак": sid_asc_sign, "градус": sid_asc_deg},
            "планеты": sid_planets,
        },
    }


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


class HoroscopeIn(BaseModel):
    name: str = ""
    natal: dict


@app.get("/")
def index():
    return FileResponse("index.html")


@app.get("/health")
def health():
    return {"message": "Астрель бэкенд жив!"}


@app.get("/natal")
def natal_direct(date: str, time: str, place: str, zodiac: str = "tropical"):
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


@app.post("/horoscope")
async def horoscope(payload: HoroscopeIn):
    """Гороскоп по полной сидерической натальной карте."""
    natal = payload.natal
    if not natal or "карта_сидерик" not in natal:
        return {"error": "Нет данных карты"}
    text = await generate_horoscope(payload.name, natal)
    return {"horoscope": text}
