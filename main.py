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

def _lon(natal, key):
    obj = natal.get("асцендент") if key == "асцендент" else (natal.get("планеты") or {}).get(key)
    if not obj:
        return None
    try:
        return SIGNS.index(obj["знак"]) * 30 + float(obj["градус"])
    except (ValueError, KeyError, TypeError):
        return None

_ASPECTS = [("соединение", 0, 8), ("секстиль", 60, 6), ("квадрат", 90, 7), ("трин", 120, 8), ("оппозиция", 180, 8)]
_HARM = {"соединение": 0.85, "секстиль": 0.65, "трин": 1.0, "квадрат": -0.9, "оппозиция": -0.7}
_HARM_HOT = {"соединение": 0.9, "секстиль": 0.6, "трин": 0.6, "квадрат": 0.8, "оппозиция": 0.7}

_CRITERIA = [
    ("Любовь", "💞", [("Венера", "Марс"), ("Венера", "Венера"), ("Луна", "Луна"), ("Солнце", "Луна")], False, 1.3),
    ("Интеллект", "🧠", [("Меркурий", "Меркурий"), ("Меркурий", "асцендент"), ("Меркурий", "Юпитер")], False, 1.0),
    ("Секс", "🔥", [("Марс", "Венера"), ("Марс", "Марс"), ("Венера", "Плутон")], True, 1.0),
    ("Деньги", "💰", [("Венера", "Юпитер"), ("Юпитер", "Солнце"), ("Юпитер", "Сатурн")], False, 0.9),
    ("Стабильность", "🏠", [("Сатурн", "Солнце"), ("Сатурн", "Луна"), ("Солнце", "Солнце")], False, 1.1),
]

def _aspect(l1, l2):
    if l1 is None or l2 is None:
        return None
    diff = abs(l1 - l2) % 360
    if diff > 180:
        diff = 360 - diff
    best = None
    for name, angle, orb in _ASPECTS:
        dev = abs(diff - angle)
        if dev <= orb and (best is None or dev < best[2]):
            best = (name, angle, dev, orb)
    return best

def _pair_contrib(n1, n2, a, b, hot):
    harm = _HARM_HOT if hot else _HARM
    asps = [_aspect(_lon(n1, a), _lon(n2, b))]
    if a != b:
        asps.append(_aspect(_lon(n1, b), _lon(n2, a)))
    contribs, best_detail, best_strength = [], None, -1
    for asp in asps:
        if asp is None:
            contribs.append(0.0)
            continue
        name, angle, dev, orb = asp
        orb_factor = 1 - dev / orb
        c = harm.get(name, 0) * orb_factor
        contribs.append(c)
        if orb_factor > best_strength:
            best_strength, best_detail = orb_factor, (name, angle, c)
    nz = [c for c in contribs if c != 0.0]
    contrib = max(nz, key=abs) if nz else 0.0
    detail = None
    if best_detail:
        name, angle, c = best_detail
        if hot and c > 0 and name in ("квадрат", "оппозиция"):
            kind = "страсть 🔥"
        else:
            kind = "гармония" if c > 0 else "напряжение"
        detail = "%s ↔ %s: %s %d° — %s" % (a, b, name, angle, kind)
    return contrib, detail

def synastry_scores(n1, n2):
    out, total_w, total_s = [], 0.0, 0.0
    for name, emoji, pairs, hot, weight in _CRITERIA:
        contribs, details = [], []
        for a, b in pairs:
            c, d = _pair_contrib(n1, n2, a, b, hot)
            contribs.append(c)
            if d:
                details.append(d)
        ranked = sorted(contribs, key=abs, reverse=True)
        rank_w = [1.0, 0.4, 0.15]
        wsum = sum(rank_w[:len(ranked)]) or 1.0
        agg = sum(w * c for w, c in zip(rank_w, ranked)) / wsum
        score = max(3, min(97, round(50 + agg * 80)))
        out.append({"name": name, "emoji": emoji, "score": score, "details": details})
        total_s += score * weight
        total_w += weight
    overall = round(total_s / total_w) if total_w else 50
    if overall >= 85:
        label = "космическая связь ✨"
    elif overall >= 70:
        label = "стоит присмотреться ⭐"
    elif overall >= 55:
        label = "есть потенциал 🌱"
    elif overall >= 40:
        label = "придётся поработать 🛠️"
    else:
        label = "непростой союз ⚡"
    return {"overall": overall, "label": label, "criteria": out}

@app.post("/synastry")
async def synastry(payload: SynastryIn):
    if not payload.natal1 or not payload.natal2: return {"error": "Нет данных карт"}
    scores = synastry_scores(payload.natal1, payload.natal2)
    text = await generate_synastry(payload.name1, payload.natal1, payload.name2, payload.natal2, scores)
    return {"synastry": text, "scores": scores}


@app.post("/synastry/scores")
async def synastry_scores_endpoint(payload: SynastryIn):
    if not payload.natal1 or not payload.natal2:
        return {"error": "Нет данных карт"}
    return {"scores": synastry_scores(payload.natal1, payload.natal2)}
