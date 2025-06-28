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
            return r[0]["lat"], r[0]["lon"]
        else:
            print(f"⚠️ No coordinates found for {city}")
            return None
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
        if "hourly" in data:
            print(f"✅ Forecast fetched for {city}")
        return data
    except Exception as e:
        print(f"❌ Error fetching forecast for {city}:", e)
        return None

def fetch_current_weather(city):
    try:
        url = BASE_CURRENT_URL.format(city, OWM_API_KEY)
        response = requests.get(url, timeout=10)
        data = response.json()
        if response.status_code == 200 and "weather" in data:
            print(f"✅ Current weather fetched for {city}")
            return data
        print(f"⚠️ No current weather data for {city}")
        return None
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

    alerts = []
    seen = set()

    for hour in forecast["hourly"][:24]:
        temp = hour["temp"]
        pop = hour.get("pop", 0)
        desc = hour["weather"][0]["description"].lower()
        time_phrase = get_time_of_day(hour["dt"])

        # 🟦 Rain detection (more sensitive):
        if any(r in desc for r in [
                "rain", "drizzle", "showers", "thunderstorm", "mist", "light rain"
            ]) or pop >= 0.05:
            if "rain" not in seen:
                alerts.append(f"🌧️ Rain in {time_phrase}")
                seen.add("rain")

        # 🔴 Heat alert:
        if temp >= 40 and "heat" not in seen:
            alerts.append(f"🔥 Heat in {time_phrase}")
            seen.add("heat")

        # ❄️ Cold alert:
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
        short_zone = zone.replace("Telangana", "").replace("Hyderabad", "").strip()
        name = short_zone or zone
        lines.append(f"{zone}: {alert}")
    return "\n".join(lines)

def generate_ai_tweet(summary_text, date_str):
    prompt = f"""
You're a friendly Indian weather bot. Based on the forecast summary below, write 1 tweet.

Tweet requirements:
- Under 280 characters
- Start with emoji headline like: "🌦️ Telangana Weather Update – {date_str}"
- Include a few zones with 📍 and short alerts (e.g., "📍 North Telangana: 🌧️ Rain in morning")
- End with a friendly tip like "Stay safe!" or "Carry an umbrella! ☂️"
- No hashtags

Forecast summary:
\"\"\"{summary_text}\"\"\"

Tweet:
"""
    try:
        response = cohere_client.generate(
            model="command-r-plus",
            prompt=prompt.strip(),
            max_tokens=280,
            temperature=0.7,
            stop_sequences=["--"]
        )
        tweet = response.generations[0].text.strip()
        return tweet[:280]
    except Exception as e:
        print("❌ Cohere error:", e)
        return None

def generate_pleasant_weather_tweet(date_str, current_weather=None):
    prompt = f"""
You're a friendly Indian weather bot. Today’s weather in Telangana is calm.

Write 1 cheerful tweet:
- Start with emoji headline: “🌤️ Telangana Weather Update – {date_str}”
- Mention no major events expected
- Optionally include: "{current_weather}"
- End with a warm sign-off like “Enjoy your day!”

Tweet:
"""
    try:
        response = cohere_client.generate(
            model="command-r-plus",
            prompt=prompt.strip(),
            max_tokens=200,
            temperature=0.7,
            stop_sequences=["--"]
        )
        return response.generations[0].text.strip()[:280]
    except Exception as e:
        print("❌ Cohere error (pleasant):", e)
        return None

def tweet_weather():
    date_str = datetime.now().strftime("%d %b")

    tg_alerts = prepare_zone_alerts(ZONES)
    hyd_alerts = prepare_zone_alerts(HYD_ZONES)

    combined_alerts = {**tg_alerts}
    if hyd_alerts:
        combined_alerts["Hyderabad"] = next(iter(hyd_alerts.values()), None)

    current_weather_data = fetch_current_weather("Hyderabad")
    current_summary = summarize_current_weather(current_weather_data)

    if combined_alerts:
        summary_text = format_zone_summary(combined_alerts)
        if current_summary:
            summary_text = f"Current weather – {current_summary}\n\n" + summary_text

        tweet_text = generate_ai_tweet(summary_text, date_str)
        if tweet_text:
            try:
                res = client.create_tweet(text=tweet_text)
                print("✅ Weather alert tweet posted! Tweet ID:", res.data["id"])
            except tweepy.TooManyRequests:
                print("❌ Rate limit hit.")
            except Exception as e:
                print("❌ Error tweeting:", e)
        else:
            print("❌ Failed to generate weather alert tweet.")
    else:
        print("ℹ️ No alerts found – tweeting a pleasant weather update.")
        tweet_text = generate_pleasant_weather_tweet(date_str, current_summary)
        if tweet_text:
            try:
                res = client.create_tweet(text=tweet_text)
                print("✅ Pleasant weather tweet posted! Tweet ID:", res.data["id"])
            except tweepy.TooManyRequests:
                print("❌ Rate limit hit while tweeting pleasant weather.")
            except Exception as e:
                print("❌ Error tweeting pleasant weather:", e)
        else:
            print("❌ Failed to generate pleasant weather tweet.")

if __name__ == "__main__":
    tweet_weather()
