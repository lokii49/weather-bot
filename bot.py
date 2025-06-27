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
    if not forecast or "hourly" not in forecast: return []
    alerts, seen = [], set()
    for hour in forecast["hourly"][:24]:
        temp = hour["temp"]
        pop = hour.get("pop", 0)
        desc = hour["weather"][0]["description"].lower()
        time_phrase = get_time_of_day(hour["dt"])
        if ("rain" in desc or pop > 0.5) and "rain" not in seen:
            alerts.append(f"🌧️ Rain likely {time_phrase}")
            seen.add("rain")
        if temp >= 38 and "heat" not in seen:
            alerts.append(f"🔥 Heat expected {time_phrase}")
            seen.add("heat")
        if temp <= 18 and "cold" not in seen:
            alerts.append(f"❄️ Cold expected {time_phrase}")
            seen.add("cold")
    return alerts

def humanize_alerts(city, alerts):
    formats = [
        f"{city} might experience {', '.join(alerts)}.",
        f"⚠️ Heads up in {city}: {', '.join(alerts)}.",
        f"Forecast for {city}: {', '.join(alerts)}.",
        f"Conditions in {city} suggest {', '.join(alerts)}."
    ]
    return random.choice(formats)

def build_zone_summary(zones):
    summary = ""
    for zone, cities in zones.items():
        events = [humanize_alerts(city, is_significant_forecast(fetch_forecast(city)))
                  for city in cities if is_significant_forecast(fetch_forecast(city))]
        if events:
            summary += f"\n📍 {zone}:\n" + "\n".join(events) + "\n"
    return summary.strip()

def generate_ai_tweet(summary_text):
    prompt = f"""You're a smart weather bot writing friendly, concise, and human-like tweets.

Rewrite this 24-hour Telangana weather forecast into a tweet under 280 characters. Use natural emojis and make it easy to understand:

\"\"\"{summary_text}\"\"\"
Tweet:"""
    try:
        response = cohere_client.generate(
            model="command-r-plus",
            prompt=prompt,
            max_tokens=150,
            temperature=0.8,
            k=0,
            stop_sequences=["--"]
        )
        return response.generations[0].text.strip()
    except Exception as e:
        print("❌ Cohere error:", e)
        return None

def tweet_weather():
    date_str = datetime.now().strftime("%d %b %Y")
    telangana = build_zone_summary(ZONES)
    hyderabad = build_zone_summary(HYD_ZONES)

    summary = f"""Weather forecast for Telangana on {date_str}:

Telangana Zones:
{telangana or 'No significant alerts in Telangana.'}

Hyderabad Zones:
{hyderabad or 'No significant alerts in Hyderabad.'}""".strip()

    ai_tweet = generate_ai_tweet(summary)
    if not ai_tweet:
        print("⚠️ GPT fallback. Posting basic tweet.")
        ai_tweet = f"🌤️ Telangana Weather – {date_str}\n{summary[:250]}..."

    try:
        if len(ai_tweet) <= 280:
            res = client.create_tweet(text=ai_tweet)
            print("✅ Tweeted successfully! Tweet ID:", res.data["id"])
        else:
            print("⚠️ Tweet too long. Skipping post.")
    except tweepy.TooManyRequests:
        print("❌ Rate limit hit. Try again later.")

if __name__ == "__main__":
    tweet_weather()
