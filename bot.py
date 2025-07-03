import os, json, random, cohere
from datetime import datetime, timedelta
import requests, pytz
from github import Github, InputFileContent
import tweepy
from dotenv import load_dotenv

load_dotenv()

# API keys
WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")
WEATHERBIT_KEY = os.getenv("WEATHERBIT_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
GIST_TOKEN = os.getenv("GIST_TOKEN")
GIST_ID = os.getenv("GIST_ID")

IST = pytz.timezone("Asia/Kolkata")
co = cohere.Client(COHERE_API_KEY)

# Twitter Auth
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
        res = requests.get(f"http://api.weatherapi.com/v1/forecast.json", params={
            "key": WEATHERAPI_KEY,
            "q": f"{city},Telangana",
            "days": 1,
            "aqi": "yes",
            "alerts": "no"
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

def detect_alerts(city):
    now = datetime.now(IST)
    cutoff = now + timedelta(hours=9)
    alerts = []

    wapi = fetch_weatherapi(city)
    owm = fetch_openweather(city)
    wb = fetch_weatherbit(city)

    def format_alert(t, cond, precip, prob, temp, vis, wind, aqi, humidity, src):
        time_label = t.strftime('%I:%M %p')
        return (
            f"{cond} at {time_label} — "
            f"{temp}°C, 🌧️{precip}mm ({prob}%), "
            f"💨{round(wind)}km/h, 🌫️{vis}km, "
            f"💧{humidity}%, AQI {aqi} [{src}]"
        )

    try:
        for hour in wapi.get("forecast", {}).get("forecastday", [{}])[0].get("hour", []):
            t = datetime.strptime(hour["time"], "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC).astimezone(IST)
            if now <= t <= cutoff:
                aqi = hour.get("air_quality", {}).get("pm2_5", 50)
                alert = format_alert(t, hour.get("condition", {}).get("text", ""), hour.get("precip_mm", 0),
                                     hour.get("chance_of_rain", 0), hour.get("temp_c", 0), hour.get("vis_km", 10),
                                     hour.get("wind_kph", 0), int(aqi), hour.get("humidity", 60), "WeatherAPI")
                alerts.append(alert)
                break
    except Exception as e:
        print(f"[WeatherAPI error for {city}]:", e)

    try:
        for hour in owm.get("list", []):
            t = datetime.utcfromtimestamp(hour["dt"]).replace(tzinfo=pytz.UTC).astimezone(IST)
            if now <= t <= cutoff:
                alert = format_alert(t, hour.get("weather", [{}])[0].get("description", ""), hour.get("rain", {}).get("3h", 0),
                                     int(hour.get("pop", 0) * 100), hour.get("main", {}).get("temp", 0),
                                     hour.get("visibility", 10000) / 1000, hour.get("wind", {}).get("speed", 0) * 3.6,
                                     60, hour.get("main", {}).get("humidity", 60), "OpenWeather")
                alerts.append(alert)
                break
    except Exception as e:
        print(f"[OpenWeather error for {city}]:", e)

    try:
        for hour in wb.get("data", []):
            t = datetime.strptime(hour["timestamp_local"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=IST)
            if now <= t <= cutoff:
                alert = format_alert(t, hour.get("weather", {}).get("description", ""), hour.get("precip", 0),
                                     hour.get("pop", 0), hour.get("temp", 0), hour.get("vis", 10),
                                     hour.get("wind_spd", 0) * 3.6, 55, hour.get("rh", 60), "Weatherbit")
                alerts.append(alert)
                break
    except Exception as e:
        print(f"[Weatherbit error for {city}]:", e)

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
    prompt = f"""Write a concise tweet about Telangana weather on {date}.
Format:
⚠️ Weather Update – {date}
📍 Zone: Condition at Time — Temp°C, 🌧️Rain (Prob%), 💨Wind, 🌫️Vis, 💧Humidity, AQI [Source]

Use only real data from below. Include 2–4 zones. Add a 1-line safety tip at the end. Do NOT invent anything.
Limit to 280 characters max.

Summaries:
{summary}

Tweet:"""

    try:
        print("\n🧠 Prompt to Cohere:\n", prompt)

        res = co.generate(
            model="command-r-plus",
            prompt=prompt,
            max_tokens=300,
            temperature=0.5,
            stop_sequences=["\n\n"]
        )

        tweet = res.generations[0].text.strip()

        print("\n📢 Raw Cohere Response:\n", tweet)
        print(f"\n📏 Generated tweet length: {len(tweet)}")

        # Remove any "Tweet:" prefix
        if tweet.lower().startswith("tweet:"):
            tweet = tweet.split(":", 1)[1].strip()

        # Validation: too short or missing zones
        if len(tweet) < 100 or "📍" not in tweet:
            print("⚠️ Tweet too short or missing alerts. Skipping.")
            return None

        # Trim if slightly over
        if len(tweet) > 280:
            tweet = tweet[:277] + "..."

        return tweet

    except Exception as e:
        print("❌ Cohere error:", e)
        return None

def main():
    print("📡 Fetching alerts...")
    all_alerts = []
    all_zones = list(HYD_ZONES.items()) + list(ZONES.items())

    for zone, cities in all_zones:
        for city in cities:
            alerts = detect_alerts(city)
            if alerts:
                print(f"✅ Alert in {city}: {alerts[0]}")
                all_alerts.append(f"📍 {zone}: {alerts[0]}")
                break

    if not all_alerts:
        print("✅ No alerts.")
        return

    summary = "\n".join(sorted(all_alerts)[:4])
    print("\n🧾 Summary passed to tweet generator:\n", summary)

    last = load_last_summary()
    now_str = datetime.now(IST).strftime('%d %b %I:%M %p')

    if last.get("summary") == summary:
        print("⏳ No new alert.")
        return

    if not summary or len(summary.strip()) < 30:
        print("⚠️ Summary too short. Skipping generation.")
        return

    tweet_text = generate_tweet(summary, now_str)

    if tweet_text:
        lines = tweet_text.strip().splitlines()
        if len(lines) < 2 or len(tweet_text.strip()) < 50:
            print("⚠️ Tweet too short or missing alerts. Skipping.")
            return

        tweet(tweet_text)
        save_summary({"summary": summary, "timestamp": datetime.now(IST).isoformat()})
    else:
        print("⚠️ Tweet generation failed. Skipping post.")

if __name__ == "__main__":
    main()