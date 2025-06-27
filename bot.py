import os
import requests
import tweepy
import logging
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime

# ==== Setup ====
load_dotenv(dotenv_path=Path('.') / '.env')
logging.basicConfig(level=logging.INFO)

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
if not API_KEY:
    raise EnvironmentError("❌ Missing OpenWeatherMap API key in environment variables.")

GEOCODE_URL = "http://api.openweathermap.org/geo/1.0/direct?q={}&limit=1&appid={}"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/onecall?lat={}&lon={}&exclude=minutely,current,alerts&units=metric&appid={}"

# Cache for coordinates
city_coords_cache = {}

def get_coords(city):
    if city in city_coords_cache:
        return city_coords_cache[city]
    try:
        r = requests.get(GEOCODE_URL.format(city, API_KEY), timeout=10).json()
        if not r:
            logging.warning(f"⚠️ No coordinates found for {city}")
            return None
        lat, lon = r[0]["lat"], r[0]["lon"]
        city_coords_cache[city] = (lat, lon)
        return lat, lon
    except Exception as e:
        logging.error(f"Error fetching coordinates for {city}: {e}")
        return None

def fetch_forecast(city):
    coords = get_coords(city)
    if not coords:
        return None
    lat, lon = coords
    try:
        r = requests.get(FORECAST_URL.format(lat, lon, API_KEY), timeout=10).json()
        return r  # contains 'hourly', 'daily'
    except Exception as e:
        logging.error(f"Error fetching forecast for {city}: {e}")
        return None

def is_significant_forecast(forecast):
    if not forecast or "daily" not in forecast:
        return []

    alerts = []
    today = forecast["daily"][0]
    max_temp = today["temp"]["max"]
    min_temp = today["temp"]["min"]
    desc = today["weather"][0]["description"].lower()
    pop = today.get("pop", 0)
    rain = today.get("rain", 0)

    if "rain" in desc or rain > 1 or pop > 0.5:
        alerts.append("🌧️ Rain")
    if max_temp >= 38:
        alerts.append("🔥 Heat")
    if min_temp <= 18:
        alerts.append("❄️ Cold")

    return alerts

# ==== FORMAT WEATHER BULLETIN ====
def build_zone_summary_forecast(zones):
    summary = ""
    for zone, cities in zones.items():
        events = []
        for city in cities:
            forecast = fetch_forecast(city)
            alerts = is_significant_forecast(forecast)
            if alerts:
                alert_str = ", ".join(alerts)
                events.append(f"{city} – {alert_str}")
        if events:
            summary += f"\n📍 {zone}:\n" + "\n".join(events) + "\n"
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
def tweet_weather_forecast():
    date_str = datetime.now().strftime("%d %b %Y")
    telangana = build_zone_summary_forecast(ZONES)
    hyderabad = build_zone_summary_forecast(HYD_ZONES)

    tweet = f"🌤️ Telangana Weather Forecast – {date_str}\n"
    tweet += telangana or "\n✅ No significant weather alerts in Telangana today.\n"
    if hyderabad:
        tweet += f"\n🏙️ Hyderabad Zones:\n{hyderabad}"

    # Trim if tweet is too long
    if len(tweet) > 280:
        tweet = tweet[:275] + "..."

    res = client.create_tweet(text=tweet)
    print("✅ Tweeted successfully! Tweet ID:", res.data["id"])

# ==== EXECUTE ONCE ====
if __name__ == "__main__":
    tweet_weather_forecast()
