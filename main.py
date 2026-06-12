from tarot import generate_horoscope, generate_synastry
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
    try: yield db
    finally: db.close()

SIGNS = ["Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева", "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы"]
PLANETS = { "Солнце": swe.SUN, "Луна": swe.MOON, "Меркурий": swe.MERCURY, "Венера": swe.VENUS, "Марс": swe.MARS, "Юпитер": swe.JUPITER, "Сатурн": swe.SATURN, "Уран": swe.URANUS, "Нептун": swe.NEPTUNE, "Плутон": swe.PLUTO }

geolocator = Nominatim(user_agent="astrel-app")
tf = TimezoneFinder()

def deg_to_sign(deg):
    deg = deg % 360
    return SIGNS[int(deg // 30)], round(deg % 30, 2)

def compute_natal(date: str, time: str, place: str, zodiac: str = "tropical"):
    location = geolocator.geocode(place)
    if location is None: raise HTTPException(status_code=404, detail=f"Не нашёл место: {place}")
    lat, lon = location.latitude, location.longitude

    tzname = tf.timezone_at(lat=lat, lng=lon)
    if tzname is None: raise HTTPException(status_code=404, detail="Не определил часовой пояс")

    year, month, day = map(int, date.split("-"))
    hour, minute = map(int, time.split(":"))
    dt = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(tzname))
    tz_offset = dt.utcoffset().total_seconds() / 3600
    jd = swe.julday(year, month, day, hour + minute / 60 - tz_offset)

    flag = swe.FLG_MOSEPH | swe.FLG_SPEED
    if zodiac == "sidereal":
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
        flag |= swe.FLG_SIDEREAL

    planets = {}
    for name, code in PLANETS.items():
        pos, _ = swe.calc_ut(jd, code, flag)
        s, d = deg_to_sign(pos[0])
        planets[name] = {"знак": s, "градус": d}

    cusps, ascmc = swe.houses_ex(jd, lat, lon, b'P', swe.FLG_SIDEREAL) if zodiac == "sidereal" else swe.houses(jd, lat, lon, b'P')
    asc_sign, asc_deg = deg_to_sign(ascmc[0])

    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    sid_flag = swe.FLG_MOSEPH | swe.FLG_SPEED | swe.FLG_SIDEREAL
    sid_planets = {}
    for name, code in PLANETS.items():
        pos, _ = swe.calc_ut(jd, code, sid_flag)
        s, d = deg_to_sign(pos[0])
        sid_planets[name] = {"знак": s, "градус": d}
    sid_cusps, sid_ascmc = swe.houses_ex(jd, lat, lon, b'P', swe.FLG_SIDEREAL)
    sid_asc_sign, sid_asc_deg = deg_to_sign(sid_ascmc[0])

    sun_trop, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_MOSEPH)
    sun_trop_sign, _ = deg_to_sign(sun_trop[0])

    return {
        "место": location.address, "часовой_пояс": tzname, "зодиак": zodiac,
        "асцендент": {"знак": asc_sign, "градус": asc_deg}, "планеты": planets,
        "солнце_тропик": sun_trop_sign, "солнце_сидерик": sid_planets["Солнце"]["знак"],
        "карта_сидерик": {"асцендент": {"знак": sid_asc_sign, "градус": sid_asc_deg}, "планеты": sid_planets},
    }

class HoroscopeIn(BaseModel):
    name: str = ""
    natal: dict

class SynastryIn(BaseModel):
    name1: str = ""
    natal1: dict
    name2: str = ""
    natal2: dict

@app.get("/")
def index(): return FileResponse("index.html")

@app.get("/health")
def health(): return {"message": "Астрель бэкенд жив!"}

@app.get("/natal")
def natal_direct(date: str, time: str, place: str, zodiac: str = "tropical"):
    return compute_natal(date, time, place, zodiac)

@app.post("/horoscope")
async def horoscope(payload: HoroscopeIn):
    if not payload.natal or "карта_сидерик" not in payload.natal: return {"error": "Нет данных карты"}
    text = await generate_horoscope(payload.name, payload.natal)
    return {"horoscope": text}

@app.post("/synastry")
async def synastry(payload: SynastryIn):
    if not payload.natal1 or not payload.natal2: return {"error": "Нет данных карт"}
    text = await generate_synastry(payload.name1, payload.natal1, payload.name2, payload.natal2)
    return {"synastry": text}
