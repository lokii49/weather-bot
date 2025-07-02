import os, json, random, cohere
from datetime import datetime, timedelta
import requests, pytz
from github import Github, InputFileContent
import tweepy
from dotenv import load_dotenv

load_dotenv()

# Load environment variables
WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")
GIST_TOKEN = os.getenv("GIST_TOKEN")
GIST_ID = os.getenv("GIST_ID")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
co = cohere.Client(COHERE_API_KEY)

TWEEPY_CLIENT = tweepy.Client(
    bearer_token=os.getenv("BEARER_TOKEN"),
    consumer_key=os.getenv("API_KEY"),
    consumer_secret=os.getenv("API_SECRET"),
    access_token=os.getenv("ACCESS_TOKEN"),
    access_token_secret=os.getenv("ACCESS_SECRET")
)

IST = pytz.timezone("Asia/Kolkata")

ZONES = {
    "North Telangana": ["Adilabad", "Nirmal", "Asifabad", "Mancherial", "Kamareddy"],
    "South Telangana": ["Mahabubnagar", "Gadwal", "Wanaparthy", "Nagarkurnool", "Narayanpet"],
    "East Telangana": ["Khammam", "Bhadrachalam", "Mahabubabad", "Warangal", "Suryapet"],
    "West Telangana": ["Vikarabad", "Sangareddy", "Zaheerabad"],
    "Central Telangana": ["Hyderabad", "Medchal", "Siddipet", "Nalgonda", "Karimnagar"]
}

HYD_ZONES = {
    "North Hyderabad": ["Kompally", "Medchal", "Suchitra", "Bolarum"],
    "South Hyderabad": ["LB Nagar", "Malakpet", "Falaknuma", "Kanchanbagh"],
    "East Hyderabad": ["Uppal", "Ghatkesar", "Keesara"],
    "West Hyderabad": ["Gachibowli", "Kondapur", "Madhapur", "Miyapur"],
    "Central Hyderabad": ["Secunderabad", "Begumpet", "Nampally", "Abids"]
}

TONE_TEMPLATES = {
    "witty": """
You are a witty Hyderabad local who loves puns.
Write ONE tweet (<280 chars) about the forecast below.

Rules:
- Start with a playful headline, e.g. “Rain, rain, go a‑Hydera‑way ☔ – {date}”
- Mention 2‑4 zone alerts using 📍
- Light humour or wordplay is welcome
- End with a cheeky sign‑off (e.g., “Chai‑me for updates! ☕”)
""",
    "friendly": """
You’re a friendly Indian neighbour sharing today’s weather.
Tweet requirements:
- Warm greeting + date, e.g. “Morning folks!  {date}”
- 2‑4 zone alerts with 📍
- Simple emojis allowed
- End with a caring tip ( “Stay hydrated!” etc.)
""",
    "alert": """
Adopt a crisp, alert‑style tone (like emergency services).
Tweet rules:
- Headline: “⚠️ Weather Alert – {date}”
- Bullet‑like zone alerts (📍)
- No humour, be direct
- Finish with a safety CTA (“Travel only if needed.”)
""",
    "telugu": """
Switch to a casual Telugu‑English mix (“Teluglish”).
Tweet rules:
- Open with a Telugu greeting + date, e.g. “శుభోదయం! {date}”
- Zone alerts with 📍; include at least one Telugu phrase (“వర్షం వస్తోంది!” etc.)
- End with a friendly Telugu sign‑off (“జాగ్రత్త!”)
"""
}

def fetch_weatherapi(city):
    url = "http://api.weatherapi.com/v1/forecast.json"
    params = {
        "key": WEATHERAPI_KEY,
        "q": f"{city}, Telangana",
        "days": 1,
        "alerts": "yes",
        "aqi": "yes"
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        return res.json() if res.status_code == 200 else None
    except:
        return None

def fetch_openweather(city):
    try:
        geocode_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city},Telangana,IN&limit=1&appid={OPENWEATHER_KEY}"
        geo_res = requests.get(geocode_url).json()
        if not geo_res:
            return None
        lat, lon = geo_res[0]['lat'], geo_res[0]['lon']

        weather_url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=metric&appid={OPENWEATHER_KEY}"
        res = requests.get(weather_url)
        return res.json() if res.status_code == 200 else None
    except:
        return None

def fetch_weatherbit(city):
    try:
        geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city},Telangana,IN&limit=1&appid={OPENWEATHER_KEY}"
        geo = requests.get(geo_url).json()
        if not geo:
            return None
        lat, lon = geo[0]['lat'], geo[0]['lon']

        wb_url = f"https://api.weatherbit.io/v2.0/forecast/hourly"
        params = {
            "lat": lat,
            "lon": lon,
            "key": os.getenv("WEATHERBIT_KEY"),
            "hours": 12  # fetch next 12 hours
        }
        res = requests.get(wb_url, params=params, timeout=10)
        return res.json() if res.status_code == 200 else None
    except:
        return None

def fetch_weatherbit_current(city):
    try:
        geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city},Telangana,IN&limit=1&appid={OPENWEATHER_KEY}"
        geo = requests.get(geo_url).json()
        if not geo:
            return None
        lat, lon = geo[0]['lat'], geo[0]['lon']

        url = "https://api.weatherbit.io/v2.0/current"
        params = {
            "lat": lat,
            "lon": lon,
            "key": os.getenv("WEATHERBIT_KEY")
        }
        res = requests.get(url, params=params, timeout=10)
        return res.json() if res.status_code == 200 else None
    except:
        return None

def fetch_weatherbit_current(city):
    try:
        geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city},Telangana,IN&limit=1&appid={OPENWEATHER_KEY}"
        geo = requests.get(geo_url).json()
        if not geo:
            return None
        lat, lon = geo[0]['lat'], geo[0]['lon']

        url = "https://api.weatherbit.io/v2.0/current"
        params = {
            "lat": lat,
            "lon": lon,
            "key": os.getenv("WEATHERBIT_KEY")
        }
        res = requests.get(url, params=params, timeout=10)
        return res.json() if res.status_code == 200 else None
    except:
        return None

def detect_alerts(city):
    now = datetime.now(IST)
    cutoff = now + timedelta(hours=9)
    alerts = []

    # Fetch data
    wapi = fetch_weatherapi(city)
    owm = fetch_openweather(city)
    wb = fetch_weatherbit(city)
    wb_now = fetch_weatherbit_current(city)

    def process_hour(t, cond, precip, prob, temp, vis, wind, label_src):
        time_label = t.strftime('%I %p')
        cond = cond.lower()

        if "heavy rain" in cond or precip > 10:
            return (f"🌧️ Heavy rain expected in {city} at {time_label} ({prob}% chance) [{label_src}]", "rain")
        elif "moderate rain" in cond or (5 < precip <= 10):
            return (f"🌦️ Moderate rain expected in {city} at {time_label} ({prob}% chance) [{label_src}]", "rain")
        elif "light rain" in cond or "drizzle" in cond or (0 < precip <= 5):
            return (f"🌦️ Drizzle in {city} at {time_label} ({prob}% chance) [{label_src}]", "rain")
        elif "thunder" in cond:
            return (f"⛈️ Thunderstorm expected in {city} at {time_label} ({prob}% chance) [{label_src}]", "rain")
        elif "haze" in cond or "mist" in cond or "smoke" in cond:
            return (f"🌫️ Hazy conditions in {city} at {time_label} [{label_src}]", "fog")
        elif "fog" in cond or vis < 2:
            return (f"🌁 Fog risk in {city} at {time_label} [{label_src}]", "fog")
        elif wind > 35:
            return (f"💨 Strong wind in {city} at {time_label} ({round(wind)} km/h) [{label_src}]", "wind")
        elif temp >= 40:
            return (f"🔥 Heatwave in {city} at {time_label} ({temp}°C) [{label_src}]", "heat")
        return None

    # WeatherAPI
    try:
        for hour in wapi.get("forecast", {}).get("forecastday", [{}])[0].get("hour", []):
            t = datetime.strptime(hour["time"], "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC).astimezone(IST)
            if now <= t <= cutoff:
                alert = process_hour(
                    t, hour.get("condition", {}).get("text", ""),
                    hour.get("precip_mm", 0),
                    hour.get("chance_of_rain", 0),
                    hour.get("temp_c", 0),
                    hour.get("vis_km", 10),
                    hour.get("wind_kph", 0),
                    "WeatherAPI"
                )
                if alert:
                    alerts.append(alert)
                    break
    except: pass

    # OpenWeather
    try:
        for hour in owm.get("list", []):
            t = datetime.utcfromtimestamp(hour["dt"]).replace(tzinfo=pytz.UTC).astimezone(IST)
            if now <= t <= cutoff:
                alert = process_hour(
                    t, hour.get("weather", [{}])[0].get("description", ""),
                    hour.get("rain", {}).get("3h", 0),
                    int(hour.get("pop", 0) * 100),
                    hour.get("main", {}).get("temp", 0),
                    hour.get("visibility", 10000) / 1000,
                    hour.get("wind", {}).get("speed", 0) * 3.6,
                    "OpenWeather"
                )
                if alert:
                    alerts.append(alert)
                    break
    except: pass

    # Weatherbit Hourly
    try:
        for hour in wb.get("data", []):
            t = datetime.strptime(hour["timestamp_local"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=IST)
            if now <= t <= cutoff:
                alert = process_hour(
                    t, hour.get("weather", {}).get("description", ""),
                    hour.get("precip", 0),
                    hour.get("pop", 0),
                    hour.get("temp", 0),
                    hour.get("vis", 10),
                    hour.get("wind_spd", 0) * 3.6,
                    "Weatherbit"
                )
                if alert:
                    alerts.append(alert)
                    break
    except: pass

    # Weatherbit Current fallback
    if not alerts and wb_now and wb_now.get("data"):
        try:
            d = wb_now["data"][0]
            alert = process_hour(
                now, d.get("weather", {}).get("description", ""),
                d.get("precip", 0),
                100,
                d.get("temp", 0),
                d.get("vis", 10),
                d.get("wind_spd", 0) * 3.6,
                "Weatherbit Now"
            )
            if alert:
                alerts.append(alert)
        except: pass

    return alerts

def load_last_summary():
    if not GIST_TOKEN or not GIST_ID:
        return {}
    g = Github(GIST_TOKEN)
    try:
        gist = g.get_gist(GIST_ID)
        file = gist.files.get("last_alert.json")
        return json.loads(file.content) if file and file.content else {}
    except:
        return {}

def save_summary(data):
    if not GIST_TOKEN or not GIST_ID:
        return
    g = Github(GIST_TOKEN)
    gist = g.get_gist(GIST_ID)
    gist.edit(files={"last_alert.json": InputFileContent(json.dumps(data))})

def tweet(text):
    try:
        res = TWEEPY_CLIENT.create_tweet(text=text)
        print("✅ Tweeted successfully:", res.data["id"])
    except Exception as e:
        print("❌ Tweet error:", e)

def main():
    print("📡 Checking weather data...")
    all_alerts = []
    has_rain = False

    all_zones = list(HYD_ZONES.items()) + list(ZONES.items())
    for zone, cities in all_zones:
        for city in cities:
            city_alerts = detect_alerts(city)
            if city_alerts:
                eng, category = city_alerts[0]
                if category == "rain":
                    has_rain = True
                all_alerts.append(f"📍 {zone}: {eng}")
                break

    if not all_alerts:
        print("✅ No alerts found. Skipping tweet.")
        return

    summary = "\n\n".join(sorted(all_alerts))
    last = load_last_summary()
    now_str = datetime.now(IST).strftime('%d %b %I:%M %p')

    # Always generate tweet for display
    tweet_text = generate_tweet(summary, now_str, tone="witty")

    print("\n📢 Tweet content:\n")
    print(tweet_text if tweet_text else "❌ Failed to generate tweet.")

    # Only skip actual tweet if already posted
    if last.get("summary") == summary:
        print("⏳ Alert already posted. Skipping tweet API call.")
        return

    if tweet_text:
        tweet(tweet_text)
        save_summary({"summary": summary, "timestamp": datetime.now(IST).isoformat()})

def generate_tweet(summary, date, tone="alert"):
    import cohere

    COHERE_API_KEY = os.getenv("COHERE_API_KEY")
    co = cohere.Client(COHERE_API_KEY)

    TONE_TEMPLATES = {
        "witty": """
You are a witty Hyderabad local who loves puns.
Write ONE tweet (<280 chars) about the forecast below.

Rules:
- Start with a playful headline, e.g. “Rain, rain, go a‑Hydera‑way ☔ – {date}”
- Mention 2‑4 zone alerts using 📍
- Light humour or wordplay is welcome
- End with a cheeky sign‑off (e.g., “Chai‑me for updates! ☕”)
""",
        "friendly": """
You’re a friendly Indian neighbour sharing today’s weather.
Tweet requirements:
- Warm greeting + date, e.g. “Morning folks!  {date}”
- 2‑4 zone alerts with 📍
- Simple emojis allowed
- End with a caring tip ( “Stay hydrated!” etc.)
""",
        "alert": """
Adopt a crisp, alert‑style tone (like emergency services).
Tweet rules:
- Headline: “⚠️ Weather Alert – {date}”
- Bullet‑like zone alerts (📍)
- No humour, be direct
- Finish with a safety CTA (“Travel only if needed.”)
""",
        "telugu": """
Switch to a casual Telugu‑English mix (“Teluglish”).
Tweet rules:
- Open with a Telugu greeting + date, e.g. “శుభోదయం! {date}”
- Zone alerts with 📍; include at least one Telugu phrase (“వర్షం వస్తోంది!” etc.)
- End with a friendly Telugu sign‑off (“జాగ్రత్త!”)
"""
    }

    template = TONE_TEMPLATES.get(tone)
    if not template:
        raise ValueError("Invalid tone selected.")

    prompt = f"""{template.strip()}

Forecast summary:
{summary}

Write tweet:"""

    try:
        response = co.generate(
            model="command-r",
            prompt=prompt,
            max_tokens=150,
            temperature=0.8,
            stop_sequences=["\n\n"]
        )
        tweet = response.generations[0].text.strip()
        return tweet[:277] + "..." if len(tweet) > 280 else tweet
    except Exception as e:
        print("❌ Cohere error:", e)
        return None

if __name__ == "__main__":
    main()
