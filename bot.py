import os
import requests
import tweepy
import random
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
import pytz

# ==== Load ENV ====
#load_dotenv(dotenv_path=Path('.') / '.env')
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

# ==== API Keys ====
OWM_API_KEY = os.getenv("OWM_API_KEY")
#openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
openai_client = os.getenv("OPENAI_API_KEY")

# ==== Tweepy Client ====
client = tweepy.Client(
    bearer_token=os.getenv("BEARER_TOKEN"),
    consumer_key=os.getenv("API_KEY"),
    consumer_secret=os.getenv("API_SECRET"),
    access_token=os.getenv("ACCESS_TOKEN"),
    access_token_secret=os.getenv("ACCESS_SECRET")
)

# ==== Weather API URL ====
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

    return alerts

# ==== HUMANIZED CITY ALERT ====
def humanize_alerts(city, alerts):
    patterns = [
        f"{city} might experience {', '.join(alerts)}.",
        f"⚠️ Heads up in {city}: {', '.join(alerts)}.",
        f"Forecast for {city}: {', '.join(alerts)}.",
        f"Conditions in {city} suggest {', '.join(alerts)}."
    ]
    return random.choice(patterns)

# ==== BUILD SUMMARY ====
def build_zone_summary(zones):
    summary = ""
    for zone, cities in zones.items():
        events = []
        for city in cities:
            forecast = fetch_forecast(city)
            alerts = is_significant_forecast(forecast)
            if alerts:
                events.append(humanize_alerts(city, alerts))
        if events:
            summary += f"\n📍 {zone}:\n" + "\n".join(events) + "\n"
    return summary.strip()

# ==== GPT TWEET GENERATOR ====
def generate_ai_tweet(summary_text):
    prompt = f"""
You're a smart weather bot writing friendly, concise, and human-like tweets.

Rewrite this 24-hour Telangana weather forecast into a tweet under 280 characters. Use natural emojis and make it easy to understand:

\"\"\"{summary_text}\"\"\"
Tweet:
"""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful weather bot writing engaging Twitter updates."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("❌ OpenAI error:", e)
        return None

# ==== TWEET THREAD POSTING ====
def post_tweet_thread(text, client):
    chunks = []
    while len(text) > 275:
        cut = text[:275].rfind('\n')
        if cut == -1:
            cut = 275
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    chunks.append(text)

    tweet = client.create_tweet(text=chunks[0])
    last_id = tweet.data["id"]

    for chunk in chunks[1:]:
        tweet = client.create_tweet(text=chunk, in_reply_to_tweet_id=last_id)
        last_id = tweet.data["id"]

    print("✅ Tweeted thread successfully.")

# ==== MAIN TWEET FUNCTION ====
def tweet_weather():
    date_str = datetime.now().strftime("%d %b %Y")

    telangana = build_zone_summary(ZONES)
    hyderabad = build_zone_summary(HYD_ZONES)

    summary_for_ai = f"""
Weather forecast for Telangana on {date_str}:

Telangana Zones:
{telangana if telangana else 'No significant alerts.'}

Hyderabad Zones:
{hyderabad if hyderabad else 'No significant alerts.'}
"""

    ai_tweet = generate_ai_tweet(summary_for_ai)

    if not ai_tweet:
        print("⚠️ GPT fallback. Posting basic tweet.")
        ai_tweet = f"🌤️ Telangana Weather – {date_str}\n{summary_for_ai[:250]}..."

    if len(ai_tweet) > 280:
        post_tweet_thread(ai_tweet, client)
    else:
        res = client.create_tweet(text=ai_tweet)
        print("✅ Tweeted successfully! Tweet ID:", res.data["id"])

# ==== RUN ====
if __name__ == "__main__":
    tweet_weather()
