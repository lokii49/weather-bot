import os
import requests
import tweepy
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
import pytz

# ==== Load ENV ====
load_dotenv(dotenv_path=Path('.') / '.env')

# ==== ZONES ====
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

# ==== API ====
OWM_API_KEY = os.getenv("OWM_API_KEY")
BASE_FORECAST_URL = "https://api.openweathermap.org/data/2.5/onecall?lat={}&lon={}&exclude=minutely&appid={}&units=metric"

# ==== GEOLOCATION ====
def get_coordinates(city):
    try:
        url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={OWM_API_KEY}"
        r = requests.get(url, timeout=10).json()
        if not r:
            return None
        return r[0]["lat"], r[0]["lon"]
    except:
        return None

# ==== FETCH FORECAST ====
def fetch_forecast(city):
    coords = get_coordinates(city)
    if not coords:
        return None
    lat, lon = coords
    try:
        url = BASE_FORECAST_URL.format(lat, lon, OWM_API_KEY)
        r = requests.get(url, timeout=10).json()
        return r
    except:
        return None

# ==== TIME OF DAY LABEL ====
def get_time_of_day(dt_unix):
    tz = pytz.timezone("Asia/Kolkata")
    hour = datetime.fromtimestamp(dt_unix, tz).hour
    if 0 <= hour <= 2:
        return "midnight"
    elif 3 <= hour <= 6:
        return "early morning"
    elif 7 <= hour <= 10:
        return "morning"
    elif 11 <= hour <= 12:
        return "late morning"
    elif 13 <= hour <= 15:
        return "afternoon"
    elif 16 <= hour <= 17:
        return "late afternoon"
    elif 18 <= hour <= 20:
        return "evening"
    elif 21 <= hour <= 23:
        return "night"
    return "sometime"

# ==== SIGNIFICANT WEATHER LOGIC ====
def is_significant_forecast(forecast):
    if not forecast or "daily" not in forecast or "hourly" not in forecast:
        return []

    alerts = []
    seen_types = set()

    # Hourly: next 24h
    for hour in forecast["hourly"][:24]:
        temp = hour["temp"]
        pop = hour.get("pop", 0)
        desc = hour["weather"][0]["description"].lower()
        time_phrase = get_time_of_day(hour["dt"])

        if "rain" in desc or pop > 0.5:
            if "rain" not in seen_types:
                alerts.append(f"🌧️ Rain likely {time_phrase}")
                seen_types.add("rain")
        if temp >= 38 and "heat" not in seen_types:
            alerts.append(f"🔥 Heat expected {time_phrase}")
            seen_types.add("heat")
        if temp <= 18 and "cold" not in seen_types:
            alerts.append(f"❄️ Cold expected {time_phrase}")
            seen_types.add("cold")

    # Daily: next 2 days
    for day in forecast["daily"][1:3]:
        max_temp = day["temp"]["max"]
        min_temp = day["temp"]["min"]
        desc = day["weather"][0]["description"].lower()
        pop = day.get("pop", 0)
        rain = day.get("rain", 0)

        if "rain" not in seen_types and ("rain" in desc or pop > 0.5 or rain > 1):
            alerts.append("🌧️ Rain expected in coming days")
            seen_types.add("rain")
        if "heat" not in seen_types and max_temp >= 38:
            alerts.append("🔥 Heatwave in coming days")
            seen_types.add("heat")
        if "cold" not in seen_types and min_temp <= 18:
            alerts.append("❄️ Cold spell likely in coming days")
            seen_types.add("cold")

    return alerts

# ==== BUILD SUMMARY ====
def build_zone_summary(zones):
    summary = ""
    for zone, cities in zones.items():
        events = []
        for city in cities:
            forecast = fetch_forecast(city)
            alerts = is_significant_forecast(forecast)
            if alerts:
                events.append(f"{city} – " + ", ".join(alerts))
        if events:
            summary += f"\n📍 {zone}:\n" + "\n".join(events) + "\n"
    return summary.strip()

# ==== TWITTER ====
client = tweepy.Client(
    bearer_token=os.getenv("BEARER_TOKEN"),
    consumer_key=os.getenv("API_KEY"),
    consumer_secret=os.getenv("API_SECRET"),
    access_token=os.getenv("ACCESS_TOKEN"),
    access_token_secret=os.getenv("ACCESS_SECRET")
)

# ==== COMPOSE AND POST ====
def tweet_weather():
    date_str = datetime.now().strftime("%d %b %Y")
    tweet = f"🌤️ Telangana Weather Forecast – {date_str}\n"

    telangana = build_zone_summary(ZONES)
    hyderabad = build_zone_summary(HYD_ZONES)

    tweet += telangana if telangana else "\n✅ No major weather alerts in Telangana.\n"
    if hyderabad:
        tweet += "\n🏙️ Hyderabad Zones:\n" + hyderabad

    if len(tweet) > 280:
        tweet = tweet[:275] + "..."

    res = client.create_tweet(text=tweet)
    print("✅ Tweeted successfully! Tweet ID:", res.data["id"])

# ==== RUN ====
if __name__ == "__main__":
    tweet_weather()
