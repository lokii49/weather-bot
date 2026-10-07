import argparse
import hashlib
import json
import math
import os
import statistics
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import anthropic
import requests
import tweepy
from dotenv import load_dotenv

load_dotenv()

IST = ZoneInfo("Asia/Kolkata")

# Coordinates verified against OpenStreetMap Nominatim; all fall inside Telangana.
ZONES = {
    "North Telangana": {
        "Adilabad": (19.6759, 78.5340), "Nirmal": (19.0915, 78.3966), "Asifabad": (19.3593, 79.2960),
        "Mancherial": (18.9813, 79.5198), "Kamareddy": (18.3166, 78.0539),
    },
    "South Telangana": {
        "Mahabubnagar": (16.6966, 77.9591), "Gadwal": (16.2347, 77.7946), "Wanaparthy": (16.2853, 77.9864),
        "Nagarkurnool": (16.4158, 78.6830), "Narayanpet": (16.7006, 77.6165),
    },
    "East Telangana": {
        "Khammam": (17.2465, 80.1500), "Bhadrachalam": (17.6688, 80.8940), "Mahabubabad": (17.7139, 80.0413),
        "Warangal": (17.9821, 79.5971), "Suryapet": (17.0800, 79.7925),
    },
    "West Telangana": {
        "Vikarabad": (17.2703, 77.7453), "Sangareddy": (17.8684, 77.8227), "Zaheerabad": (17.6794, 77.6153),
    },
    "Central Telangana": {
        "Hyderabad": (17.3606, 78.4741), "Medchal": (17.6340, 78.4843), "Siddipet": (18.0056, 78.8961),
        "Nalgonda": (17.0504, 79.2669), "Karimnagar": (18.4348, 79.1328),
    },
}

HYD_ZONES = {
    "North Hyderabad": {
        "Kompally": (17.5401, 78.4909), "Suchitra": (17.5023, 78.4838), "Bolarum": (17.5298, 78.5155),
    },
    "South Hyderabad": {
        "LB Nagar": (17.3502, 78.5511), "Malakpet": (17.3737, 78.4996), "Falaknuma": (17.3327, 78.4752),
        "Kanchanbagh": (17.3281, 78.5002),
    },
    "East Hyderabad": {
        "Uppal": (17.4025, 78.5613), "Ghatkesar": (17.4511, 78.6843), "Keesara": (17.5249, 78.6665),
    },
    "West Hyderabad": {
        "Gachibowli": (17.4436, 78.3520), "Kondapur": (17.4588, 78.3731), "Madhapur": (17.4409, 78.3916),
        "Miyapur": (17.4982, 78.3568),
    },
    "Central Hyderabad": {
        "Secunderabad": (17.4337, 78.5007), "Begumpet": (17.4462, 78.4630), "Nampally": (17.3924, 78.4701),
        "Abids": (17.3895, 78.4772),
    },
}

ALL_ZONES = {**ZONES, **HYD_ZONES}
CITIES = {city: coords for cities in ALL_ZONES.values() for city, coords in cities.items()}

# Forecast window and event thresholds
LOOKAHEAD_HOURS = 12
RAIN_MM = 0.5          # mm/h that counts as rain for a single source
RAIN_POP = 50          # % precipitation probability that counts as rain for a single source
HEAVY_RAIN_MM = 7.5    # median mm/h across sources (IMD "heavy" is ~7.5 mm/h)
HEAT_C = 40
COLD_C = 20

# Duplicate suppression
DEDUP_HOURS = 6
CALM_DEDUP_HOURS = 12

OPEN_METEO_MODELS = {
    "ecmwf": "ecmwf_ifs025",
    "gfs": "gfs_seamless",
    "icon": "icon_seamless",
}

CLAUDE_MODEL = "claude-opus-5-5"
MAX_TWEET_WEIGHT = 280

OWM_API_KEY = os.getenv("OPENWEATHER_KEY")
WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY")
GIST_ID = os.getenv("GIST_ID")
GIST_TOKEN = os.getenv("GIST_TOKEN")
LAST_TWEET_FILENAME = "last_tweet.json"

HTTP = requests.Session()


# ---------------------------------------------------------------------------
# Forecast sources. Each returns {city: [point, ...]} where a point is
# {"ts": aware IST datetime on the hour, "temp", "pop" (0-100 or None),
#  "precip" (mm/h), "rainy" (bool), "thunder" (bool)}.
# ---------------------------------------------------------------------------

def _hour(dt):
    return dt.astimezone(IST).replace(minute=0, second=0, microsecond=0)


def _wmo_flags(code):
    code = int(code or 0)
    thunder = code >= 95
    rainy = thunder or 51 <= code <= 67 or 80 <= code <= 82
    return rainy, thunder


def fetch_open_meteo():
    """One request covers every city and every model."""
    names = list(CITIES)
    params = {
        "latitude": ",".join(str(CITIES[n][0]) for n in names),
        "longitude": ",".join(str(CITIES[n][1]) for n in names),
        "hourly": "temperature_2m,precipitation_probability,precipitation,weather_code",
        "current": "temperature_2m,relative_humidity_2m,weather_code",
        "models": ",".join(OPEN_METEO_MODELS.values()),
        "timezone": "Asia/Kolkata",
        "forecast_hours": LOOKAHEAD_HOURS + 2,
    }
    try:
        response = HTTP.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print("❌ Open-Meteo error:", e)
        return {}, {}

    if isinstance(data, dict):
        data = [data]

    by_source = {source: {} for source in OPEN_METEO_MODELS}
    current = {}
    for name, loc in zip(names, data):
        hourly = loc.get("hourly", {})
        times = [datetime.fromisoformat(t).replace(tzinfo=IST) for t in hourly.get("time", [])]
        for source, model in OPEN_METEO_MODELS.items():
            temps = hourly.get(f"temperature_2m_{model}") or []
            pops = hourly.get(f"precipitation_probability_{model}") or [None] * len(times)
            precs = hourly.get(f"precipitation_{model}") or []
            codes = hourly.get(f"weather_code_{model}") or []
            points = []
            for i, ts in enumerate(times):
                if i >= len(temps) or temps[i] is None:
                    continue
                rainy, thunder = _wmo_flags(codes[i] if i < len(codes) else 0)
                points.append({
                    "ts": ts,
                    "temp": temps[i],
                    "pop": pops[i] if i < len(pops) else None,
                    "precip": (precs[i] if i < len(precs) else 0) or 0,
                    "rainy": rainy,
                    "thunder": thunder,
                })
            if points:
                by_source[source][name] = points

        cur = loc.get("current") or {}
        temp = next((v for k, v in cur.items() if k.startswith("temperature_2m") and v is not None), None)
        hum = next((v for k, v in cur.items() if k.startswith("relative_humidity_2m") and v is not None), None)
        code = next((v for k, v in cur.items() if k.startswith("weather_code") and v is not None), None)
        if temp is not None:
            current[name] = {"temp_c": temp, "humidity": hum, "wmo_code": code}

    for source, cities in by_source.items():
        print(f"✅ Open-Meteo {source}: {len(cities)}/{len(names)} cities")
    return by_source, current


def _owm_city(name):
    lat, lon = CITIES[name]
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": OWM_API_KEY, "units": "metric", "cnt": LOOKAHEAD_HOURS // 3 + 2}
    response = HTTP.get(url, params=params, timeout=10)
    response.raise_for_status()
    points = []
    for item in response.json().get("list", []):
        start = _hour(datetime.fromtimestamp(item["dt"], IST))
        weather_id = item["weather"][0]["id"]
        thunder = 200 <= weather_id < 300
        rainy = thunder or 300 <= weather_id < 600
        precip = item.get("rain", {}).get("3h", 0) / 3
        # 3-hour step: spread over its three hours
        for offset in range(3):
            points.append({
                "ts": start + timedelta(hours=offset),
                "temp": item["main"]["temp"],
                "pop": item.get("pop", 0) * 100,
                "precip": precip,
                "rainy": rainy,
                "thunder": thunder,
            })
    return points


def _weatherapi_city(name):
    lat, lon = CITIES[name]
    url = "https://api.weatherapi.com/v1/forecast.json"
    params = {"key": WEATHERAPI_KEY, "q": f"{lat},{lon}", "days": 2, "aqi": "no", "alerts": "no"}
    response = HTTP.get(url, params=params, timeout=10)
    response.raise_for_status()
    points = []
    for day in response.json()["forecast"]["forecastday"]:
        for hour in day["hour"]:
            text = hour["condition"]["text"].lower()
            thunder = "thunder" in text
            points.append({
                "ts": _hour(datetime.fromtimestamp(hour["time_epoch"], IST)),
                "temp": hour["temp_c"],
                "pop": hour.get("chance_of_rain"),
                "precip": hour.get("precip_mm", 0) or 0,
                "rainy": thunder or any(w in text for w in ("rain", "drizzle", "shower")),
                "thunder": thunder,
            })
    return points


def _fetch_per_city(label, fn):
    def safe(name):
        try:
            return name, fn(name)
        except Exception as e:
            print(f"⚠️ {label} failed for {name}: {type(e).__name__} {e}")
            return name, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = {name: pts for name, pts in pool.map(safe, CITIES) if pts}
    print(f"{'✅' if results else '❌'} {label}: {len(results)}/{len(CITIES)} cities")
    return results


def fetch_all_sources():
    sources, current = fetch_open_meteo()
    if OWM_API_KEY:
        sources["openweathermap"] = _fetch_per_city("OpenWeatherMap", _owm_city)
    else:
        print("ℹ️ OPENWEATHER_KEY not set – skipping OpenWeatherMap")
    if WEATHERAPI_KEY:
        sources["weatherapi"] = _fetch_per_city("WeatherAPI", _weatherapi_city)
    else:
        print("ℹ️ WEATHERAPI_KEY not set – skipping WeatherAPI")
    return {s: cities for s, cities in sources.items() if cities}, current


# ---------------------------------------------------------------------------
# Consensus event detection
# ---------------------------------------------------------------------------

def _is_wet(point):
    pop = point["pop"]
    return (
        point["precip"] >= RAIN_MM
        or (pop is not None and pop >= RAIN_POP)
        or (point["rainy"] and point["precip"] >= 0.1)
    )


def _votes_needed(n):
    # At least two sources must agree (when two or more report), and a majority when many do.
    return max(min(2, n), math.ceil(n / 2))


def detect_city_events(city, sources, now):
    """Returns {label: [(hour, confidence, value), ...]} for the lookahead window.

    value is the median precip (mm/h) for rain events and the median temp for heat/cold.
    """
    start, end = _hour(now), _hour(now) + timedelta(hours=LOOKAHEAD_HOURS)
    by_hour = defaultdict(list)
    for cities in sources.values():
        for point in cities.get(city, []):
            if start <= point["ts"] <= end:
                by_hour[point["ts"]].append(point)

    events = defaultdict(list)
    for ts in sorted(by_hour):
        points = by_hour[ts]
        n = len(points)
        wet = [p for p in points if _is_wet(p)]
        if len(wet) >= _votes_needed(n):
            confidence = len(wet) / n
            median_precip = statistics.median(p["precip"] for p in points)
            if sum(p["thunder"] for p in wet) >= _votes_needed(n):
                events["thunderstorm"].append((ts, confidence, median_precip))
            elif median_precip >= HEAVY_RAIN_MM:
                events["heavy_rain"].append((ts, confidence, median_precip))
            else:
                events["rain"].append((ts, confidence, median_precip))

        median_temp = statistics.median(p["temp"] for p in points)
        if median_temp >= HEAT_C:
            events["heat"].append((ts, 1.0, median_temp))
        if median_temp <= COLD_C:
            events["cold"].append((ts, 1.0, median_temp))
    return events


def _windows(hours):
    """Collapse sorted hours into (start, end) windows, bridging gaps of up to two dry hours."""
    windows = []
    for ts in sorted(set(hours)):
        if windows and ts - windows[-1][1] <= timedelta(hours=3):
            windows[-1][1] = ts
        else:
            windows.append([ts, ts])
    return [(s, e) for s, e in windows]


def time_of_day(dt):
    h = dt.hour
    if h < 5:
        return "late night"
    if h < 8:
        return "early morning"
    if h < 12:
        return "morning"
    if h < 16:
        return "afternoon"
    if h < 19:
        return "evening"
    return "night"


def describe_window(start, end, now):
    def label(dt):
        part = time_of_day(dt)
        if dt.date() == now.date():
            return "tonight" if part == "night" else part
        if dt.date() == now.date() + timedelta(days=1):
            return f"tomorrow {part}" if part not in ("late night",) else "overnight"
        return f"{dt:%a} {part}"

    clock = f"{start:%-I %p}–{(end + timedelta(hours=1)):%-I %p}"
    first, last = label(start), label(end)
    return {"when": first if first == last else f"{first} to {last}", "clock": clock}


def _intensity(label, values):
    if label in ("heat", "cold"):
        return f"{round(max(values) if label == 'heat' else min(values))}°C"
    peak = max(values)
    if label == "heavy_rain" or peak >= HEAVY_RAIN_MM:
        return "heavy"
    return "moderate" if peak >= 2.5 else "light"


def build_zone_alerts(sources, now):
    zone_alerts = {}
    for zone, cities in ALL_ZONES.items():
        hits = defaultdict(list)  # label -> [(ts, city, confidence, value)]
        for city in cities:
            for label, city_hits in detect_city_events(city, sources, now).items():
                hits[label].extend((ts, city, conf, value) for ts, conf, value in city_hits)

        alerts = []
        for label, label_hits in hits.items():
            for start, end in _windows(h[0] for h in label_hits):
                in_window = [h for h in label_hits if start <= h[0] <= end]
                affected = sorted({h[1] for h in in_window})
                alerts.append({
                    "event": label,
                    "intensity": _intensity(label, [h[3] for h in in_window]),
                    **describe_window(start, end, now),
                    "start": start,
                    "places": affected,
                    "coverage": f"{len(affected)}/{len(cities)} locations",
                    "model_agreement": f"{round(100 * statistics.mean(h[2] for h in in_window))}%",
                })
        if alerts:
            alerts.sort(key=lambda a: a["start"])
            zone_alerts[zone] = alerts
            print(f"🔍 {zone}: " + "; ".join(f"{a['intensity']} {a['event']} {a['when']}" for a in alerts))
    return zone_alerts


def alert_signature(zone_alerts):
    """Coarse fingerprint so small timing shifts don't count as a new forecast."""
    items = sorted(
        (zone, a["event"], a["start"].date().isoformat(), time_of_day(a["start"]))
        for zone, alerts in zone_alerts.items()
        for a in alerts
    )
    return hashlib.sha256(json.dumps(items).encode()).hexdigest()[:16] if items else "calm"


# ---------------------------------------------------------------------------
# Tweet generation with Claude
# ---------------------------------------------------------------------------

WMO_CONDITIONS = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
    80: "Light showers", 81: "Showers", 82: "Heavy showers", 95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}

SYSTEM_PROMPT = """You are the forecast desk for a weather account covering Telangana and Hyderabad, India. You turn a structured forecast into one tweet.

The forecast comes from up to five weather models (ECMWF, GFS, ICON, OpenWeatherMap, WeatherAPI). An event appears only when several models agree, so treat every event in the data as real and report nothing beyond it.

Voice: a professional weather service, in the manner of IMD or a newsroom weather desk. Factual, calm, specific. Readers act on these posts, so precision matters more than personality: no rhymes, jokes, puns, exclamation marks, rhetorical flourishes, or sign-offs such as "Stay safe!".

Format:
1. Header: "<emoji> Telangana Weather | <Day> <D> <Mon>, <H> <AM/PM>" using local_time rounded down to the hour. Pick the emoji for the most severe event: ⛈️ thunderstorm, 🌧️ heavy or moderate rain, 🌦️ light rain, 🔥 heat, 🌡️ cold, 🌤️ nothing significant.
2. A blank line, then one line per area, most severe first (thunderstorm > heavy rain > heat > rain > cold):
   "📍 <Area>: <Intensity> <event> <when> (<clock>)"
   - Combine zones that share the same event and timing ("📍 North & East Telangana: ...").
   - Name one or two places from "places" when coverage is partial ("Moderate rain around Warangal, Khammam tonight (8–11 PM)").
   - Write Hyderabad zones as "Hyderabad" when all of them share the event, otherwise as "West Hyderabad" etc.
3. If Hyderabad has no alert, add: "📍 Hyderabad: <condition>, <temp>°C" from hyderabad_now.
4. Only for thunderstorms, heavy rain, or heat, end with one short advisory line starting with "⚠️" (e.g. "⚠️ Avoid open areas and trees during lightning.").

Use the 12-hour clock ranges as given. Shorten zone names ("N Telangana", "W Hyd") only if needed to fit. No hashtags, links, or quotation marks. Hard limit 260 characters, with each emoji counting as 2.

Example (alerts):
⛈️ Telangana Weather | Wed 7 Oct, 6 PM

📍 East Telangana: Thunderstorms around Khammam, Bhadrachalam tonight (8–11 PM)
📍 South Telangana: Light rain overnight (1–4 AM)
📍 Hyderabad: Partly cloudy, 27°C

⚠️ Avoid open areas and trees during lightning.

Example (no alerts):
🌤️ Telangana Weather | Thu 8 Oct, 9 AM

No significant rain, heat or cold expected across Telangana in the next 12 hours.
📍 Hyderabad: Mainly clear, 29°C

Reply with the tweet text only."""


def tweet_weight(text):
    """Approximates X's weighted length: most non-Latin characters and emoji count as 2."""
    weight = 0
    for ch in text:
        cp = ord(ch)
        if 0xFE00 <= cp <= 0xFE0F or cp == 0x200D:
            continue
        if cp <= 0x10FF or 0x2000 <= cp <= 0x200D or 0x2010 <= cp <= 0x201F or 0x2032 <= cp <= 0x2037:
            weight += 1
        else:
            weight += 2
    return weight


def _ask_claude(client, user_content):
    response = client.beta.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        print(f"❌ Claude stopped with {response.stop_reason}")
        return None
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text.strip('"').strip() or None


def generate_tweet(zone_alerts, current, now):
    hyd_now = current.get("Hyderabad")
    if hyd_now:
        hyd_now = {
            "condition": WMO_CONDITIONS.get(int(hyd_now["wmo_code"] or 0), "Clear"),
            "temp_c": round(hyd_now["temp_c"]),
        }
    payload = {
        "local_time": now.strftime("%a %-d %b, %-I:%M %p IST"),
        "forecast_window_hours": LOOKAHEAD_HOURS,
        "hyderabad_now": hyd_now,
        "alerts_by_zone": {
            zone: [{k: v for k, v in a.items() if k != "start"} for a in alerts]
            for zone, alerts in zone_alerts.items()
        },
    }
    base = f"Forecast data:\n{json.dumps(payload, indent=2, ensure_ascii=False)}"

    try:
        client = anthropic.Anthropic()
        tweet = _ask_claude(client, base)
        if tweet and tweet_weight(tweet) > MAX_TWEET_WEIGHT:
            print(f"✂️ Draft too long ({tweet_weight(tweet)}), asking for a shorter one")
            tweet = _ask_claude(
                client,
                f"{base}\n\nA previous draft was {tweet_weight(tweet)} weighted characters, over the limit. "
                f"Write a tighter version under 250 weighted characters:\n{tweet}",
            )
    except anthropic.APIError as e:
        print(f"❌ Claude API error: {type(e).__name__} {e}")
        return None

    if tweet and tweet_weight(tweet) > MAX_TWEET_WEIGHT:
        print(f"❌ Tweet still too long ({tweet_weight(tweet)}) – not posting")
        return None
    return tweet


# ---------------------------------------------------------------------------
# State (GitHub Gist) and posting
# ---------------------------------------------------------------------------

def _gist_headers():
    return {"Authorization": f"token {GIST_TOKEN}", "Accept": "application/vnd.github+json"}


def load_last_tweet():
    if not (GIST_ID and GIST_TOKEN):
        return None
    try:
        response = HTTP.get(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(), timeout=10)
        response.raise_for_status()
        file = response.json().get("files", {}).get(LAST_TWEET_FILENAME)
        return json.loads(file["content"]) if file else None
    except Exception as e:
        print("⚠️ Couldn't load last tweet:", e)
        return None


def save_last_tweet(text, signature, now):
    payload = {"files": {LAST_TWEET_FILENAME: {"content": json.dumps(
        {"text": text, "signature": signature, "posted_at": now.isoformat()}, ensure_ascii=False
    )}}}
    response = HTTP.patch(f"https://api.github.com/gists/{GIST_ID}", headers=_gist_headers(), json=payload, timeout=10)
    print("✅ Last tweet saved to Gist" if response.ok else f"❌ Failed to save last tweet: {response.status_code}")


def is_duplicate(last, signature, now):
    if not last or last.get("signature") != signature or not last.get("posted_at"):
        return False
    window = CALM_DEDUP_HOURS if signature == "calm" else DEDUP_HOURS
    return now - datetime.fromisoformat(last["posted_at"]) < timedelta(hours=window)


def post_tweet(text):
    client = tweepy.Client(
        bearer_token=os.getenv("BEARER_TOKEN"),
        consumer_key=os.getenv("API_KEY"),
        consumer_secret=os.getenv("API_SECRET"),
        access_token=os.getenv("ACCESS_TOKEN"),
        access_token_secret=os.getenv("ACCESS_SECRET"),
    )
    res = client.create_tweet(text=text)
    print("✅ Tweet posted! ID:", res.data["id"])


def tweet_weather(dry_run=False):
    now = datetime.now(IST)
    sources, current = fetch_all_sources()
    if not sources:
        print("❌ No forecast sources returned data – aborting.")
        return
    print(f"📡 Sources in consensus: {', '.join(sources)}")

    zone_alerts = build_zone_alerts(sources, now)
    signature = alert_signature(zone_alerts)
    if not zone_alerts:
        print("ℹ️ No significant weather in the next", LOOKAHEAD_HOURS, "hours.")

    last = load_last_tweet()
    if is_duplicate(last, signature, now):
        print(f"⏭️ Same forecast ({signature}) already tweeted at {last['posted_at']} – skipping.")
        return

    if dry_run and not os.getenv("ANTHROPIC_API_KEY"):
        print("🧪 Dry run without ANTHROPIC_API_KEY – stopping before tweet generation.")
        return

    tweet = generate_tweet(zone_alerts, current, now)
    if not tweet:
        print("❌ Failed to generate tweet.")
        return

    print(f"\n📝 Tweet ({tweet_weight(tweet)}/{MAX_TWEET_WEIGHT}):\n{tweet}\n")
    if dry_run:
        print("🧪 Dry run – not posting or saving state.")
        return

    try:
        post_tweet(tweet)
    except tweepy.TooManyRequests:
        print("❌ Rate limit hit.")
        return
    except Exception as e:
        print("❌ Error tweeting:", e)
        return
    save_last_tweet(tweet, signature, now)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Post a Telangana/Hyderabad weather tweet.")
    parser.add_argument("--dry-run", action="store_true", help="Print the tweet without posting or writing state")
    args = parser.parse_args()
    tweet_weather(dry_run=args.dry_run or os.getenv("DRY_RUN") == "1")
