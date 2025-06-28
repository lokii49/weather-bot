import os
import requests
import tweepy
import cohere
from dotenv import load_dotenv
from datetime import datetime
import pytz

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

def extract_alerts(data):
    alerts = []
    forecast_hours = data.get("forecast", {}).get("forecastday", [{}])[0].get("hour", [])
    seen = set()

    for hour in forecast_hours:
        temp = hour.get("temp_c", 0)
        humidity = hour.get("humidity", 0)
        condition = hour.get("condition", {}).get("text", "").lower()
        precip_mm = hour.get("precip_mm", 0)
        wind_kph = hour.get("wind_kph", 0)
        visibility_km = hour.get("vis_km", 10)
        time_str = hour.get("time", "")
        hour_dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        hour_text = hour_dt.strftime("%I %p").lstrip("0")

        if any(r in condition for r in ["rain", "drizzle", "showers", "thunder"]):
            if "rain" not in seen:
                alerts.append(f"🌧️ Rain expected around {hour_text}")
                seen.add("rain")
        if temp >= 38 and "heat" not in seen:
            alerts.append(f"🔥 High heat around {hour_text}")
            seen.add("heat")
        if temp <= 20 and "cold" not in seen:
            alerts.append(f"❄️ Cold weather around {hour_text}")
            seen.add("cold")
        if humidity >= 70 and "humid" not in seen:
            alerts.append(f"🌫️ Humid air around {hour_text}")
            seen.add("humid")
        if wind_kph >= 25 and "windy" not in seen:
            alerts.append(f"💨 Windy conditions around {hour_text}")
            seen.add("windy")
        if visibility_km < 2 and "fog" not in seen:
            alerts.append(f"🌁 Fog expected {hour_text}")
            seen.add("fog")

    aqi = data.get("current", {}).get("air_quality", {}).get("pm2_5", 0)
    if aqi >= 60 and "pollution" not in seen:
        alerts.append("🟤 Poor air quality – limit outdoor time")
        seen.add("pollution")

    return alerts

def get_zone_alerts(zones):
    zone_alerts = {}
    for zone, cities in zones.items():
        for city in cities:
            data = fetch_weatherapi_forecast(city)
            if not data:
                continue
            alerts = extract_alerts(data)
            if alerts:
                zone_alerts[zone] = alerts[0]  # Only one alert per zone
                break
    return zone_alerts

def format_zone_summary(zone_alerts):
    lines = []
    for zone, alert in zone_alerts.items():
        lines.append(f"📍 {zone}: {alert}")
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
        {summary_text}

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
        return response.generations[0].text.strip()[:280]
    except:
        return None

def tweet_weather():
    date_str = datetime.now().strftime("%d %b")
    tg_alerts = get_zone_alerts(ZONES)
    hyd_alerts = get_zone_alerts(HYD_ZONES)

    combined_alerts = {**tg_alerts}
    if hyd_alerts:
        combined_alerts["Hyderabad"] = next(iter(hyd_alerts.values()), None)

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
