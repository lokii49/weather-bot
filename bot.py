import os
import requests
import tweepy
import cohere
from dotenv import load_dotenv
from datetime import datetime
import pytz
import random

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

def get_coordinates(city):
    try:
        url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={OWM_API_KEY}"
        r = requests.get(url, timeout=10).json()
        return (r[0]["lat"], r[0]["lon"]) if r else None
    except:
        return None

def fetch_forecast(city):
    coords = get_coordinates(city)
    if not coords:
        return None
    try:
        url = BASE_FORECAST_URL.format(*coords, OWM_API_KEY)
        return requests.get(url, timeout=10).json()
    except:
        return None

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

        # 🌧️ Better rain detection: include drizzle/light rain and lower pop
        if any(r in desc for r in ["rain", "drizzle", "showers"]) or pop >= 0.3:
            if "rain" not in seen:
                alerts.append(f"🌧️ Rain in {time_phrase}")
                seen.add("rain")

        # 🔥 Heat alert
        if temp >= 36 and "heat" not in seen:
            alerts.append(f"🔥 Heat in {time_phrase}")
            seen.add("heat")

        # ❄️ Cold alert
        if temp <= 20 and "cold" not in seen:
            alerts.append(f"❄️ Cold in {time_phrase}")
            seen.add("cold")

    return alerts

def prepare_zone_alerts(zones):
    zone_alerts = {}
    for zone, cities in zones.items():
        for city in cities:
            forecast = fetch_forecast(city)
            alerts = is_significant_forecast(forecast)
            if alerts:
                zone_alerts[zone] = alerts[0]  # Take first significant alert
                break
    return zone_alerts

def format_zone_summary(zone_alerts):
    lines = []
    for zone, alert in zone_alerts.items():
        short_zone = zone.replace("Telangana", "").replace("Hyderabad", "").strip()
        name = short_zone or zone
        lines.append(f"{zone}: {alert}")
    return "\n".join(lines)

def generate_ai_tweets(summary_text, date_str, num_variants=3):
    prompt = f"""
You're a friendly Indian weather bot. Based on the forecast summary below, write {num_variants} tweet variations.

Each tweet must:
- Be under 280 characters
- Start with a weather emoji headline like: "🌦️ Telangana Weather Update – {date_str}"
- Include a few zones with bullet-point emojis like 📍 and a short weather alert (e.g., "📍 North Telangana: 🌧️ Rain in morning")
- End with a friendly tip (e.g., "Stay safe!" or "Carry an umbrella! ☂️")
- Do NOT use hashtags

Forecast summary:
\"\"\"{summary_text}\"\"\"

Tweets:
1."""
    try:
        response = cohere_client.generate(
            model="command-r-plus",
            prompt=prompt,
            max_tokens=500,
            temperature=0.7,
            stop_sequences=["--"]
        )
        output = response.generations[0].text.strip()
        tweets = [line.strip("1234567890. ").strip() for line in output.split("\n") if line.strip()]
        # Ensure all tweets are ≤ 280 chars
        return [t[:280] for t in tweets if t][:num_variants]
    except Exception as e:
        print("❌ Cohere error:", e)
        return []

def tweet_weather():
    date_str = datetime.now().strftime("%d %b")
    
    # Prepare alerts
    tg_alerts = prepare_zone_alerts(ZONES)
    hyd_alerts = prepare_zone_alerts(HYD_ZONES)
    
    # Merge all alerts
    combined_alerts = {**tg_alerts, "Hyderabad": next(iter(hyd_alerts.values()), None)} if hyd_alerts else tg_alerts

    if not combined_alerts:
        print("ℹ️ No significant alerts to post.")
        return

    # Prepare summary for AI
    summary_text = format_zone_summary(combined_alerts)
    
    ai_tweets = generate_ai_tweets(summary_text, date_str, num_variants=3)
    
    if not ai_tweets:
        print("⚠️ Failed to generate AI tweets.")
        return

    for i, tweet in enumerate(ai_tweets):
        try:
            res = client.create_tweet(text=tweet)
            print(f"✅ Tweet {i+1} posted! Tweet ID:", res.data["id"])
        except tweepy.TooManyRequests:
            print("❌ Rate limit hit. Try again later.")
            break
        except Exception as e:
            print(f"❌ Error tweeting variant {i+1}:", e)

if __name__ == "__main__":
    tweet_weather()