import os
import requests
import tweepy
import cohere
from dotenv import load_dotenv
from datetime import datetime
import pytz

load_dotenv()
cohere_client = cohere.Client(os.getenv("COHERE_API_KEY"))

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

client = tweepy.Client(
    bearer_token=os.getenv("BEARER_TOKEN"),
    consumer_key=os.getenv("API_KEY"),
    consumer_secret=os.getenv("API_SECRET"),
    access_token=os.getenv("ACCESS_TOKEN"),
    access_token_secret=os.getenv("ACCESS_SECRET")
)

OWM_API_KEY = os.getenv("OWM_API_KEY")

BASE_FORECAST_URL = "https://api.openweathermap.org/data/2.5/onecall?lat={}&lon={}&exclude=minutely&appid={}&units=metric"
BASE_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather?q={}&appid={}&units=metric"

def get_coordinates(city):
    try:
        url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={OWM_API_KEY}"
        r = requests.get(url, timeout=10).json()
        if r:
            print(f"📍 {city} coords: {r[0]['lat']}, {r[0]['lon']}")
        else:
            print(f"⚠️ No coordinates found for {city}")
        return (r[0]["lat"], r[0]["lon"]) if r else None
    except Exception as e:
        print(f"❌ Coordinate lookup failed for {city}:", e)
        return None

def fetch_forecast(city):
    coords = get_coordinates(city)
    if not coords:
        return None
    try:
        url = BASE_FORECAST_URL.format(*coords, OWM_API_KEY)
        response = requests.get(url, timeout=10)
        data = response.json()
        return data if "hourly" in data else None
    except Exception as e:
        print(f"❌ Error fetching forecast for {city}:", e)
        return None

def fetch_current_weather(city):
    try:
        url = BASE_CURRENT_URL.format(city, OWM_API_KEY)
        response = requests.get(url, timeout=10)
        data = response.json()
        return data if response.status_code == 200 and "weather" in data else None
    except Exception as e:
        print(f"❌ Error fetching current weather for {city}:", e)
        return None

def summarize_current_weather(data):
    if not data:
        return None
    desc = data["weather"][0]["description"].capitalize()
    temp = data["main"]["temp"]
    city = data["name"]
    return f"{city}: {desc}, {temp}°C"

def get_time_of_day(dt_unix):
    hour = datetime.fromtimestamp(dt_unix, pytz.timezone("Asia/Kolkata")).hour
    if 0 <= hour <= 2: return "midnight"
    if 3 <= hour <= 6: return "early morning"
    if 7 <= hour <= 10: return "morning"
    if 11 <= hour <= 12: return "late morning"
    if 13 <= hour <= 15: return "afternoon"
    if 16 <= hour <= 17: return "late afternoon"
    if 18 <= hour <= 20: return "evening"
    return "night"

def is_significant_forecast(forecast):
    if not forecast or "hourly" not in forecast:
        return []

    alerts, seen = [], set()
    for hour in forecast["hourly"][:24]:
        temp = hour["temp"]
        pop = hour.get("pop", 0)
        desc = hour["weather"][0]["description"].lower()
        time_phrase = get_time_of_day(hour["dt"])

        if any(r in desc for r in ["rain", "drizzle", "showers", "thunderstorm", "mist"]) or pop >= 0.1:
            if "rain" not in seen:
                alerts.append(f"🌧️ Rain in {time_phrase}")
                seen.add("rain")
        if temp >= 40 and "heat" not in seen:
            alerts.append(f"🔥 Heat in {time_phrase}")
            seen.add("heat")
        if temp <= 20 and "cold" not in seen:
            alerts.append(f"❄️ Cold in {time_phrase}")
            seen.add("cold")
    return alerts

def prepare_zone_alerts(zones):
    zone_alerts = {}
    for zone, cities in zones.items():
        for city in cities:
            forecast = fetch_forecast(city)
            if not forecast:
                continue
            alerts = is_significant_forecast(forecast)
            print(f"🔍 {zone} / {city}: alerts={alerts}")
            if alerts:
                zone_alerts[zone] = alerts[0]
                break
    return zone_alerts

def format_zone_summary(zone_alerts):
    lines = []
    for zone, alert in zone_alerts.items():
        lines.append(f"{zone}: {alert}")
    return "\n".join(lines)

def generate_ai_tweet(summary_text, date_str):
    prompt = f"""
You're a friendly Indian weather bot. Based on the forecast summary below, write 1 tweet.

The tweet must:
- Be under 280 characters
- Start with a weather emoji headline like: "🌦️ Telangana Weather Update – {date_str}"
- Include a few zones with bullet-point emojis like 📍 and a short weather alert (e.g., "📍 North Telangana: 🌧️ Rain in morning")
- End with a friendly tip (e.g., "Stay safe!" or "Carry an umbrella! ☂️")
- Do NOT use hashtags

Forecast summary:
\"\"\"{summary_text}\"\"\"

Tweet:
"""
    try:
        response = cohere_client.generate(
            model="command-r-plus",
            prompt=prompt,
            max_tokens=280,
            temperature=0.7
        )
        tweet = response.generations[0].text.strip()
        return tweet[:280]
    except Exception as e:
        print("❌ Cohere error:", e)
        return None

def tweet_weather():
    date_str = datetime.now().strftime("%d %b")

    tg_alerts = prepare_zone_alerts(ZONES)
    hyd_alerts = prepare_zone_alerts(HYD_ZONES)

    combined_alerts = {**tg_alerts}
    if hyd_alerts:
        combined_alerts["Hyderabad"] = next(iter(hyd_alerts.values()), None)

    if not combined_alerts:
        print("ℹ️ No significant alerts to post.")
        return

    summary_text = format_zone_summary(combined_alerts)

    current_weather_data = fetch_current_weather("Hyderabad")
    current_summary = summarize_current_weather(current_weather_data)

    if current_summary:
        summary_text = f"Current weather – {current_summary}\n\n" + summary_text

    tweet = generate_ai_tweet(summary_text, date_str)
    if not tweet:
        print("⚠️ Failed to generate tweet.")
        return

    try:
        res = client.create_tweet(text=tweet)
        print(f"✅ Tweet posted! Tweet ID:", res.data["id"])
    except tweepy.TooManyRequests:
        print("❌ Rate limit hit.")
    except Exception as e:
        print("❌ Tweet failed:", e)

if __name__ == "__main__":
    tweet_weather()