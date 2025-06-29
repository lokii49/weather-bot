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

WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY")

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
user = client.get_me()
print("Authenticated as:", user.data.username)

def fetch_weatherapi_forecast(city):
    try:
        params = {
            "key": WEATHERAPI_KEY,
            "q": f"{city}, Telangana, India",
            "days": 1,
            "aqi": "yes",
            "alerts": "yes"
        }
        response = requests.get("http://api.weatherapi.com/v1/forecast.json", params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Failed to fetch data for {city}: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Exception fetching forecast for {city}: {e}")
        return None

def summarize_weather_data(data):
    if not data:
        return None

    current = data["current"]
    location = data["location"]["name"]
    condition = current["condition"]["text"]
    temp_c = current["temp_c"]
    return f"{location}: {condition}, {temp_c}°C"

def classify_aqi_level(aqi):
    levels = ["🟢 Good", "🟡 Fair", "🟠 Moderate", "🟤 Poor", "🔴 Very Poor"]
    if 0 <= aqi - 1 < len(levels):
        return levels[aqi - 1]
    return "⚪ Unknown"

def extract_alerts(data, start_hour=6, end_hour=18):
    alerts = []
    forecast_hours = data.get("forecast", {}).get("forecastday", [{}])[0].get("hour", [])
    seen = set()
    relevant_hours = []

    for hour in forecast_hours:
        time_str = hour.get("time", "")
        hour_dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        hour_only = hour_dt.hour

        if start_hour <= end_hour:
            if start_hour <= hour_only < end_hour:
                relevant_hours.append((hour_dt, hour))
        else:  # e.g., 6 PM – 6 AM
            if hour_only >= start_hour or hour_only < end_hour:
                relevant_hours.append((hour_dt, hour))

    # Define alert rules
    ALERT_RULES = [
        {
            "id": "rain",
            "check": lambda h: any(w in h.get("condition", {}).get("text", "").lower() for w in ["rain", "drizzle", "showers", "thunder"]),
            "message": lambda t: f"🌧️ Rain expected around {t}"
        },
        {
            "id": "heat",
            "check": lambda h: h.get("temp_c", 0) >= 38,
            "message": lambda t: f"🔥 High heat around {t}"
        },
        {
            "id": "cold",
            "check": lambda h: h.get("temp_c", 0) <= 20,
            "message": lambda t: f"❄️ Cold weather around {t}"
        },
        {
            "id": "humid",
            "check": lambda h: h.get("humidity", 0) >= 70,
            "message": lambda t: f"🌫️ Humid air around {t}"
        },
        {
            "id": "windy",
            "check": lambda h: h.get("wind_kph", 0) >= 25,
            "message": lambda t: f"💨 Windy conditions around {t}"
        },
        {
            "id": "fog",
            "check": lambda h: h.get("vis_km", 10) < 2,
            "message": lambda t: f"🌁 Fog expected around {t}"
        },
    ]

    for hour_dt, hour in relevant_hours:
        hour_text = hour_dt.strftime("%I %p").lstrip("0")
        for rule in ALERT_RULES:
            if rule["id"] not in seen and rule["check"](hour):
                alerts.append(rule["message"](hour_text))
                seen.add(rule["id"])

    # Handle AQI (outside hourly loop)
    aqi_pm25 = data.get("current", {}).get("air_quality", {}).get("pm2_5", 0)
    if aqi_pm25 >= 60 and "pollution" not in seen:
        alerts.append("🟤 Poor air quality – limit outdoor time")
        seen.add("pollution")

    return alerts

def get_zone_alerts(zones, start_hour, end_hour):
    zone_alerts = {}
    for zone, cities in zones.items():
        for city in cities:
            data = fetch_weatherapi_forecast(city)
            if not data:
                continue
            alerts = extract_alerts(data, start_hour=start_hour, end_hour=end_hour)
            if alerts:
                zone_alerts[zone] = alerts[0]
                break
    return zone_alerts

def format_zone_summary(zone_alerts):
    lines = []
    for zone, alert in zone_alerts.items():
        lines.append(f"📍 {zone}: {alert}")
    return "\n".join(lines)

def generate_ai_tweet(summary_text, date_str):
    styles = [
        f"""
You're a friendly Indian weather bot. Based on the forecast summary below, write a concise tweet.

Requirements:
- Start with something like "🌦️ Telangana Weather – {date_str}" or "Weather today ☁️ – {date_str}"
- Use casual tone, can include emojis like ☁️ 🌧️ 🔥 💨
- Include 2–4 zones with alerts like: "📍 East Telangana: Rain at 8 AM"
- End with a friendly tip or local phrase (e.g., "Stay cool 😎", "Umbrella might help ☂️")
""",
        f"""
Act like a cheerful Hyderabad local sharing today's weather.

Tweet should:
- Start with something fun like: "Morning update! 🌄" or "Heads up, folks! 🌧️"
- Mention weather in different Telangana zones briefly
- Use local tone, mix emojis, slight humor okay
- Be under 280 characters
- End with a tip like "Avoid travel post noon!" or "Best to wrap up early"
""",
        f"""
You're a smart weather assistant. Write a tweet summary for Telangana on {date_str}.

Include:
- 2–3 zone alerts in bullet/emoji format
- Avoid being too formal
- Add a short reminder: “Don’t forget your water bottle!” or “Air quality’s poor, stay in if you can.”
""",
    ]

    prompt = random.choice(styles).strip() + f"\n\nForecast summary:\n{summary_text}\n\nTweet:"
    
    try:
        response = cohere_client.generate(
            model="command-r-plus",
            prompt=prompt,
            max_tokens=280,
            temperature=0.9,  # slightly higher for creativity
            stop_sequences=["--"]
        )
        return response.generations[0].text.strip()[:280]
    except Exception as e:
        print("❌ AI generation error:", e)
        return None

def tweet_weather():
    IST = pytz.timezone("Asia/Kolkata")
    now = datetime.now(IST)
    date_str = now.strftime("%d %b")

    # Determine time window
    if 5 <= now.hour < 12:
        # Morning tweet: 6 AM – 6 PM
        start_hour = 6
        end_hour = 18
    else:
        # Evening tweet: 6 PM – 6 AM
        start_hour = 18
        end_hour = 6

    # Get weather alerts based on time window
    tg_alerts = get_zone_alerts(ZONES, start_hour, end_hour)
    hyd_alerts = get_zone_alerts(HYD_ZONES, start_hour, end_hour)

    # Combine Telangana + Hyderabad zone alerts
    combined_alerts = {**tg_alerts}

    # Add each Hyderabad sub-zone (like "North Hyderabad", "West Hyderabad", etc.)
    for zone, alert in hyd_alerts.items():
        combined_alerts[zone] = alert

    # Optional: Include a general "Hyderabad" alert (first alert from hyd_alerts)
    if hyd_alerts:
        combined_alerts["Hyderabad"] = next(iter(hyd_alerts.values()))

    # Format and generate tweet
    summary_text = format_zone_summary(combined_alerts)
    tweet_text = generate_ai_tweet(summary_text, date_str)

    if tweet_text:
        try:
            res = client.create_tweet(text=tweet_text)
            print("✅ Weather tweet posted! Tweet ID:", res.data["id"])
        except Exception as e:
            print("❌ Error tweeting:", e)
    else:
        print("❌ Failed to generate tweet.")

if __name__ == "__main__":
    tweet_weather()
