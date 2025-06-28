import os
import requests
import tweepy
import cohere
from dotenv import load_dotenv
from datetime import datetime
import pytz

# Load environment variables
load_dotenv()
cohere_client = cohere.Client(os.getenv("COHERE_API_KEY"))

# Zones
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

# Twitter client
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

# Forecast functions
def get_coordinates(city):
    url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={OWM_API_KEY}"
    r = requests.get(url, timeout=10).json()
    return (r[0]["lat"], r[0]["lon"]) if r else None

def fetch_forecast(city):
    coords = get_coordinates(city)
    if not coords:
        return None
    url = BASE_FORECAST_URL.format(*coords, OWM_API_KEY)
    data = requests.get(url, timeout=10).json()
    return data if "hourly" in data else None

def fetch_current_weather(city):
    url = BASE_CURRENT_URL.format(city, OWM_API_KEY)
    data = requests.get(url, timeout=10).json()
    return data if "weather" in data else None

def summarize_current_weather(data):
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
            if alerts:
                zone_alerts[zone] = alerts[0]
                break
    return zone_alerts

def format_zone_summary(zone_alerts):
    return "\n".join([f"{zone}: {alert}" for zone, alert in zone_alerts.items()])

# AI tweet generation
def generate_ai_tweet(summary_text, date_str, period):
    prompt = f"""
You're a friendly Indian weather bot. Based on the forecast summary below, write 1 tweet.

- Must be under 280 characters
- Start with a weather emoji + '{period.title()} Weather Update – {date_str}'
- Use bullet-point emojis like 📍 to show zones and alerts
- End with a short tip (e.g., "Stay safe!" or "Carry water 💧")

Forecast summary:
\"\"\"{summary_text}\"\"\"

Tweet:
"""
    try:
        response = cohere_client.generate(
            model="command-r-plus",
            prompt=prompt,
            max_tokens=300,
            temperature=0.7,
            stop_sequences=["--"]
        )
        text = response.generations[0].text.strip()
        return text[:280]
    except Exception as e:
        print("❌ Cohere error:", e)
        return None

# Main tweeting logic
def tweet_weather():
    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    date_str = now.strftime("%d %b")
    hour = now.hour

    if 5 <= hour < 12:
        period = "morning"
    elif 17 <= hour < 22:
        period = "evening"
    else:
        period = "daily"

    # Fetch alerts
    tg_alerts = prepare_zone_alerts(ZONES)
    hyd_alerts = prepare_zone_alerts(HYD_ZONES)
    combined_alerts = {**tg_alerts}
    if hyd_alerts:
        combined_alerts["Hyderabad"] = next(iter(hyd_alerts.values()), None)

    current_weather_data = fetch_current_weather("Hyderabad")
    current_summary = summarize_current_weather(current_weather_data) if current_weather_data else None

    if not combined_alerts:
        print("ℹ️ No alerts found – tweeting a pleasant weather update.")
        pleasant_prompt = f"""
You're a friendly Indian weather bot. Create 1 tweet for {period} on {date_str}.

The forecast is clear with no significant alerts. Use a cheerful tone.

Include:
- A pleasant weather emoji and intro (like 🌤️ Pleasant day ahead – 28 Jun)
- A short line about nice weather in Telangana or Hyderabad
- Optional: current weather in Hyderabad ({current_summary})
- A friendly tip (e.g., "Have a great day!" or "Perfect weather for a walk 🌿")

Limit to 280 characters. Don't use hashtags.

Tweet:
"""
        try:
            response = cohere_client.generate(
                model="command-r-plus",
                prompt=pleasant_prompt,
                max_tokens=300,
                temperature=0.7,
                stop_sequences=["--"]
            )
            tweet = response.generations[0].text.strip()[:280]
            res = client.create_tweet(text=tweet)
            print(f"✅ Pleasant tweet posted! ID: {res.data['id']}")
        except Exception as e:
            print("❌ Error tweeting pleasant weather:", e)
        return

    # Otherwise, tweet regular alert-based weather
    summary_text = format_zone_summary(combined_alerts)
    if current_summary:
        summary_text = f"Current weather – {current_summary}\n\n{summary_text}"

    tweet = generate_ai_tweet(summary_text, date_str, period)
    if not tweet:
        print("⚠️ Failed to generate tweet.")
        return

    try:
        res = client.create_tweet(text=tweet)
        print(f"✅ Alert tweet posted! ID: {res.data['id']}")
    except Exception as e:
        print("❌ Error tweeting forecast:", e)

if __name__ == "__main__":
    tweet_weather()