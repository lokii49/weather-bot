import os, json, random, cohere
from datetime import datetime, timedelta
import requests, pytz
from github import Github, InputFileContent
import tweepy
from dotenv import load_dotenv

load_dotenv()

# Environment
WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")
WEATHERBIT_KEY = os.getenv("WEATHERBIT_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
GIST_TOKEN = os.getenv("GIST_TOKEN")
GIST_ID = os.getenv("GIST_ID")

IST = pytz.timezone("Asia/Kolkata")
co = cohere.Client(COHERE_API_KEY)

TWEEPY_CLIENT = tweepy.Client(
    bearer_token=os.getenv("BEARER_TOKEN"),
    consumer_key=os.getenv("API_KEY"),
    consumer_secret=os.getenv("API_SECRET"),
    access_token=os.getenv("ACCESS_TOKEN"),
    access_token_secret=os.getenv("ACCESS_SECRET")
)

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

def fetch_weatherapi(city):
    try:
        res = requests.get("http://api.weatherapi.com/v1/forecast.json", params={
            "key": WEATHERAPI_KEY,
            "q": f"{city}, Telangana",
            "days": 1,
            "alerts": "yes",
            "aqi": "yes"
        }, timeout=10)
        return res.json() if res.status_code == 200 else None
    except:
        return None

def fetch_openweather(city):
    try:
        geo = requests.get(f"http://api.openweathermap.org/geo/1.0/direct?q={city},Telangana,IN&limit=1&appid={OPENWEATHER_KEY}").json()
        if not geo: return None
        lat, lon = geo[0]['lat'], geo[0]['lon']
        res = requests.get(f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=metric&appid={OPENWEATHER_KEY}")
        return res.json() if res.status_code == 200 else None
    except:
        return None

def fetch_weatherbit(city):
    try:
        geo = requests.get(f"http://api.openweathermap.org/geo/1.0/direct?q={city},Telangana,IN&limit=1&appid={OPENWEATHER_KEY}").json()
        if not geo: return None
        lat, lon = geo[0]['lat'], geo[0]['lon']
        res = requests.get("https://api.weatherbit.io/v2.0/forecast/hourly", params={
            "lat": lat,
            "lon": lon,
            "key": WEATHERBIT_KEY,
            "hours": 12
        }, timeout=10)
        return res.json() if res.status_code == 200 else None
    except:
        return None

def fetch_weatherbit_current(city):
    try:
        geo = requests.get(f"http://api.openweathermap.org/geo/1.0/direct?q={city},Telangana,IN&limit=1&appid={OPENWEATHER_KEY}").json()
        if not geo: return None
        lat, lon = geo[0]['lat'], geo[0]['lon']
        res = requests.get("https://api.weatherbit.io/v2.0/current", params={
            "lat": lat,
            "lon": lon,
            "key": WEATHERBIT_KEY
        }, timeout=10)
        return res.json() if res.status_code == 200 else None
    except:
        return None

def detect_alerts(city):
    now = datetime.now(IST)
    cutoff = now + timedelta(hours=9)
    alerts = []

    wapi = fetch_weatherapi(city)
    owm = fetch_openweather(city)
    wb = fetch_weatherbit(city)
    wb_now = fetch_weatherbit_current(city)

    def process_hour(t, cond, precip, prob, temp, vis, wind, src):
        time_label = t.strftime('%I %p')
        cond = cond.lower()
        if "heavy rain" in cond or precip > 10:
            return (f"🌧️ Heavy rain expected in {city} at {time_label} ({prob}% chance) [{src}]", "rain")
        elif "moderate rain" in cond or (5 < precip <= 10):
            return (f"🌦️ Moderate rain expected in {city} at {time_label} ({prob}% chance) [{src}]", "rain")
        elif "light rain" in cond or "drizzle" in cond or (0 < precip <= 5):
            return (f"🌦️ Drizzle in {city} at {time_label} ({prob}% chance) [{src}]", "rain")
        elif "thunder" in cond:
            return (f"⛈️ Thunderstorm expected in {city} at {time_label} ({prob}% chance) [{src}]", "rain")
        elif "fog" in cond or vis < 2:
            return (f"🌁 Fog risk in {city} at {time_label} [{src}]", "fog")
        elif wind > 35:
            return (f"💨 Strong wind in {city} at {time_label} ({round(wind)} km/h) [{src}]", "wind")
        elif temp >= 40:
            return (f"🔥 Heatwave in {city} at {time_label} ({temp}°C) [{src}]", "heat")
        return None

    try:
        for hour in wapi.get("forecast", {}).get("forecastday", [{}])[0].get("hour", []):
            t = datetime.strptime(hour["time"], "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC).astimezone(IST)
            if now <= t <= cutoff:
                alert = process_hour(t, hour.get("condition", {}).get("text", ""), hour.get("precip_mm", 0), hour.get("chance_of_rain", 0),
                                     hour.get("temp_c", 0), hour.get("vis_km", 10), hour.get("wind_kph", 0), "WeatherAPI")
                if alert: alerts.append(alert); break
    except: pass

    try:
        for hour in owm.get("list", []):
            t = datetime.utcfromtimestamp(hour["dt"]).replace(tzinfo=pytz.UTC).astimezone(IST)
            if now <= t <= cutoff:
                alert = process_hour(t, hour.get("weather", [{}])[0].get("description", ""), hour.get("rain", {}).get("3h", 0),
                                     int(hour.get("pop", 0) * 100), hour.get("main", {}).get("temp", 0),
                                     hour.get("visibility", 10000) / 1000, hour.get("wind", {}).get("speed", 0) * 3.6, "OpenWeather")
                if alert: alerts.append(alert); break
    except: pass

    try:
        for hour in wb.get("data", []):
            t = datetime.strptime(hour["timestamp_local"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=IST)
            if now <= t <= cutoff:
                alert = process_hour(t, hour.get("weather", {}).get("description", ""), hour.get("precip", 0), hour.get("pop", 0),
                                     hour.get("temp", 0), hour.get("vis", 10), hour.get("wind_spd", 0) * 3.6, "Weatherbit")
                if alert: alerts.append(alert); break
    except: pass

    if not alerts and wb_now and wb_now.get("data"):
        try:
            d = wb_now["data"][0]
            alert = process_hour(now, d.get("weather", {}).get("description", ""), d.get("precip", 0), 100,
                                 d.get("temp", 0), d.get("vis", 10), d.get("wind_spd", 0) * 3.6, "Weatherbit Now")
            if alert: alerts.append(alert)
        except: pass

    return alerts

def load_last_summary():
    if not GIST_TOKEN or not GIST_ID: return {}
    try:
        gist = Github(GIST_TOKEN).get_gist(GIST_ID)
        file = gist.files.get("last_alert.json")
        return json.loads(file.content) if file and file.content else {}
    except:
        return {}

def save_summary(data):
    if not GIST_TOKEN or not GIST_ID: return
    gist = Github(GIST_TOKEN).get_gist(GIST_ID)
    gist.edit(files={"last_alert.json": InputFileContent(json.dumps(data))})

def tweet(text):
    try:
        res = TWEEPY_CLIENT.create_tweet(text=text)
        print("✅ Tweeted:", res.data["id"])
    except Exception as e:
        print("❌ Tweet error:", e)

def generate_tweet(summary, date, tone="alert"):
    TEMPLATES = {
        "witty": f"""You are a witty Hyderabad local who loves puns.
Write ONE tweet (<280 chars) about the forecast below.

Rules:
- Playful headline – {date}”
- Mention 2‑4 zone alerts using 📍
- Use humour or wordplay
- End with cheeky sign‑off (e.g., “Chai‑me for updates! ☕”)

Forecast summary:
{summary}

Write tweet:""",
        "friendly": f"""You’re a friendly Indian neighbour sharing today’s weather.
Tweet must:
- Warm greet like “Morning folks! {date}”
- 2‑4 zone alerts with 📍 + emojis
- End with a caring tip

Forecast summary:
{summary}

Write tweet:""",
        "alert": f"""Write an alert-style tweet for today’s Telangana forecast.
- Format: ⚠️ Weather Alert – {date}
- List zone alerts as 📍 bullets
- No jokes. End with safety CTA

Forecast summary:
{summary}

Write tweet:""",
        "telugu": f"""Use a Telugu-English mix tweet for forecast:
- Start with Telugu greeting & {date}
- Use 📍 for alerts. Include 1 Telugu phrase (e.g., వర్షం వస్తోంది!)
- End with Telugu tip (“జాగ్రత్త!”)

Forecast summary:
{summary}

Write tweet:"""
    }

    try:
        res = co.generate(
            model="command-r-plus",  # FIXED model name
            prompt=TEMPLATES[tone],
            max_tokens=150,
            temperature=0.8,
            stop_sequences=["\n\n"]
        )
        tweet = res.generations[0].text.strip()
        return tweet[:277] + "..." if len(tweet) > 280 else tweet
    except Exception as e:
        print("❌ Cohere error:", e)
        return None

def main():
    print("📡 Checking weather data...")
    all_alerts = []
    all_zones = list(HYD_ZONES.items()) + list(ZONES.items())

    for zone, cities in all_zones:
        for city in cities:
            city_alerts = detect_alerts(city)
            if city_alerts:
                msg, _ = city_alerts[0]
                all_alerts.append(f"📍 {zone}: {msg}")
                break

    if not all_alerts:
        print("✅ No alerts. Skipping.")
        return

    # Take top 4 alerts only
    alerts_for_tweet = sorted(all_alerts)[:4]
    summary = "\n".join(alerts_for_tweet)

    last = load_last_summary()
    now_str = datetime.now(IST).strftime('%d %b %I:%M %p')

    tweet_text = generate_tweet(summary, now_str, tone="witty")  # Change tone here

    print("\n📢 Tweet content:\n")
    print(tweet_text or "❌ Failed to generate tweet.")

    if last.get("summary") == summary:
        print("⏳ Same as last tweet. Skipping.")
        return

    if tweet_text:
        tweet(tweet_text)
        save_summary({"summary": summary, "timestamp": datetime.now(IST).isoformat()})

if __name__ == "__main__":
    main()
