import os
import requests
import tweepy
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime

# Load .env variables
load_dotenv(dotenv_path=Path('.') / '.env')

# ==== ZONAL DEFINITIONS ====
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

# ==== WEATHER SETUP ====
API_KEY = os.getenv("OWM_API_KEY")
BASE_URL = "https://api.openweathermap.org/data/2.5/weather?q={}&appid={}&units=metric"

def fetch_weather(city):
    try:
        url = BASE_URL.format(city, API_KEY)
        r = requests.get(url, timeout=10).json()
        if r.get("main") is None:
            return None
        temp = r["main"]["temp"]
        desc = r["weather"][0]["description"].lower()
        return {"city": city, "temp": temp, "desc": desc}
    except:
        return None

def is_significant(weather):
    if not weather:
        return False
    return (
        "rain" in weather["desc"] or
        weather["temp"] >= 38 or
        weather["temp"] <= 18
    )

# ==== FORMAT WEATHER BULLETIN ====
def build_zone_summary(zones):
    summary = ""
    for zone, cities in zones.items():
        events = []
        for city in cities:
            w = fetch_weather(city)
            if is_significant(w):
                emoji = "🌧️" if "rain" in w["desc"] else "🔥" if w["temp"] >= 38 else "❄️"
                events.append(f"{emoji} {city} ({round(w['temp'])}°C)")
        if events:
            summary += f"\n📍 {zone}:\n" + ", ".join(events) + "\n"
    return summary

# ==== TWITTER API SETUP ====
client = tweepy.Client(
    bearer_token=os.getenv("BEARER_TOKEN"),
    consumer_key=os.getenv("API_KEY"),
    consumer_secret=os.getenv("API_SECRET"),
    access_token=os.getenv("ACCESS_TOKEN"),
    access_token_secret=os.getenv("ACCESS_SECRET")
)

# ==== COMPOSE AND POST TWEET ====
def tweet_weather():
    date_str = datetime.now().strftime("%d %b %Y")
    telangana = build_zone_summary(ZONES)
    hyderabad = build_zone_summary(HYD_ZONES)

    tweet = f"🌤️ Telangana Weather Update – {date_str}\n"
    tweet += telangana or "\nNo significant weather alerts in Telangana today.\n"
    if hyderabad:
        tweet += "\n🏙️ Hyderabad Zones:\n" + hyderabad

    if len(tweet) > 280:
        tweet = tweet[:275] + "..."

    res = client.create_tweet(text=tweet)
    print("✅ Tweeted successfully! Tweet ID:", res.data["id"])

# ==== EXECUTE ONCE ====
tweet_weather()