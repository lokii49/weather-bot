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
user = client.get_me()
print("Authenticated as:", user.data.username)

OWM_API_KEY = os.getenv("OWM_API_KEY")

BASE_FORECAST_URL = "https://api.openweathermap.org/data/2.5/onecall?lat={}&lon={}&exclude=minutely&appid={}&units=metric"
BASE_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather?q={}&appid={}&units=metric"

def get_coordinates(city):
    try:
        url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={OWM_API_KEY}"
        response = requests.get(url, timeout=10)
        
        # Handle 403 or other HTTP errors
        if response.status_code == 403:
            raise Exception("403 Forbidden from geocoding API")

        r = response.json()
        if r:
            return r[0]["lat"], r[0]["lon"]

    except Exception as e:
        print(f"⚠️ Geocoding failed for {city}: {e}")

    # Fallback for "Suchitra" – feel free to add more
    fallback_coords = {
        "Suchitra": (17.4966, 78.4475),
        "Hyderabad": (17.385044, 78.486671),
        "Secunderabad": (17.4399, 78.4983),
    }
    
    for key in fallback_coords:
        if key.lower() in city.lower():
            print(f"🧭 Using fallback coordinates for {city}: {fallback_coords[key]}")
            return fallback_coords[key]

    return None
    
def get_aqi(lat, lon, api_key):
    try:
        response = requests.get(
            "https://api.openweathermap.org/data/2.5/air_pollution",
            params={"lat": lat, "lon": lon, "appid": api_key}
        )
        if response.ok:
            return response.json()
    except:
        pass
    return None

def fetch_forecast(city):
    coords = get_coordinates(city)
    if not coords:
        print(f"❌ Could not get coordinates for {city}")
        return None, None
    lat, lon = coords
    try:
        print(f"🌐 Fetching forecast for {city} at ({lat}, {lon})")
        url = BASE_FORECAST_URL.format(lat, lon, OWM_API_KEY)
        forecast = requests.get(url, timeout=10).json()
        aqi = get_aqi(lat, lon, OWM_API_KEY)
        return forecast, aqi
    except Exception as e:
        print(f"❌ Error fetching forecast for {city}: {e}")
        return None, None

def fetch_current_weather(city):
    try:
        url = BASE_CURRENT_URL.format(city, OWM_API_KEY)
        response = requests.get(url, timeout=10)
        data = response.json()
        if response.status_code == 200 and "weather" in data:
            return data
        return None
    except:
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

def classify_aqi_level(aqi):
    levels = {
        1: "🟢 Good",
        2: "🟡 Fair",
        3: "🟠 Moderate",
        4: "🟤 Poor",
        5: "🔴 Very Poor"
    }
    return levels.get(aqi, "⚪ Unknown")

def get_worst_aqi_city(cities):
    worst_city = None
    worst_aqi = -1
    worst_level = ""

    for city in cities:
        coords = get_coordinates(city)
        if not coords:
            continue
        aqi_data = get_aqi(*coords, OWM_API_KEY)
        if not aqi_data:
            continue
        aqi = aqi_data.get("list", [{}])[0].get("main", {}).get("aqi", 1)
        if aqi > worst_aqi:
            worst_city = city
            worst_aqi = aqi
            worst_level = classify_aqi_level(aqi)

    if worst_city and worst_aqi >= 3:
        return f"{worst_city}: {worst_level} air quality"
    return None

def is_significant_forecast(forecast, aqi_data=None):
    if not forecast or "hourly" not in forecast:
        return []

    alerts = []
    seen = set()

    for hour in forecast["hourly"][:24]:
        temp = hour["temp"]
        humidity = hour.get("humidity", 0)
        feels_like = hour.get("feels_like", temp)
        pop = hour.get("pop", 0)
        desc = hour["weather"][0]["description"].lower()
        time_phrase = get_time_of_day(hour["dt"])

        print(f"🕒 {time_phrase}: temp={temp}, humidity={humidity}, feels_like={feels_like}, pop={pop}, desc='{desc}'")

        # Rain (more sensitive)
        rain_keywords = ["rain", "drizzle", "showers", "thunderstorm", "mist", "light rain", "scattered", "sprinkles"]
        if any(r in desc for r in rain_keywords) or pop >= 0.02:
            if "rain" not in seen:
                alerts.append(f"🌦️ Light rain expected {time_phrase}")
                seen.add("rain")

        # Heat
        if temp >= 38 and "heat" not in seen:
            alerts.append(f"🔥 Heat in {time_phrase}")
            seen.add("heat")

        # Humidity
        if (
            "heat" not in seen and "humid" not in seen and
            temp >= 32 and humidity >= 70 and feels_like < 40
        ):
            alerts.append(f"🌫️ Humid {time_phrase} with sticky air ({round(temp)}°C)")
            seen.add("humid")

        # Cold
        if temp <= 20 and "cold" not in seen:
            alerts.append(f"❄️ Cold in {time_phrase}")
            seen.add("cold")

        # Wind
        if hour.get("wind_speed", 0) >= 7 and "windy" not in seen:
            alerts.append(f"🌬️ Windy {time_phrase}, hold onto your hats!")
            seen.add("windy")

        # Fog
        if hour.get("visibility", 10000) <= 2000 and "fog" not in seen:
            alerts.append(f"🌁 Fog expected {time_phrase}, drive safe!")
            seen.add("fog")

    # AQI
    if aqi_data:
        aqi = aqi_data.get("list", [{}])[0].get("main", {}).get("aqi", 1)
        if aqi >= 4 and "pollution" not in seen:
            alerts.append("🟤 Poor air quality – limit outdoor time")
            seen.add("pollution")

    print(f"⚠️ Final alerts: {alerts}")
    return alerts

def prepare_zone_alerts(zones):
    zone_alerts = {}
    for zone, cities in zones.items():
        for city in cities:
            forecast, aqi_data = fetch_forecast(city)
            if not forecast:
                print(f"⚠️ Skipping {city} – no forecast data.")
                continue

            print(f"✅ Forecast keys for {city}: {list(forecast.keys())}")
            alerts = is_significant_forecast(forecast, aqi_data=aqi_data)

            print(f"🔍 {zone} / {city}: alerts={alerts}")
            if alerts:
                zone_alerts[zone] = alerts[0]
                break  # Only one alert per zone
    return zone_alerts

def format_zone_summary(zone_alerts):
    lines = []
    for zone, alert in zone_alerts.items():
        lines.append(f"{zone}: {alert}")
    return "\n".join(lines)

def generate_ai_tweet(summary_text, date_str):
    prompt = f"""
You're a friendly Indian weather bot. Based on the forecast summary below, write 1 tweet.

Tweet requirements:
- Under 280 characters
- Start with emoji headline like: \"\ud83c\udf26\ufe0f Telangana Weather Update – {date_str}\"
- Include a few zones with \ud83d\udccd and short alerts (e.g., \"\ud83d\udccd North Telangana: \ud83c\udf27\ufe0f Rain in morning\")
- End with a friendly tip like \"Stay safe!\" or \"Carry an umbrella! \u2612\ufe0f\"
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
        return response.generations[0].text.strip()[:280]
    except:
        return None

def generate_pleasant_weather_tweet(date_str, current_weather=None):
    prompt = f"""
You're a friendly Indian weather bot. Today’s weather in Telangana is calm.

Write 1 cheerful tweet:
- Start with emoji headline: “🌤️ Weather Update – {date_str}”
- Mention no major events expected
- Optionally include: \"{current_weather}\"
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
    except:
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

    summary_text = ""
    tweet_text = ""

    # Always calculate AQI info, regardless of alert status
    all_cities = sum(ZONES.values(), []) + sum(HYD_ZONES.values(), [])
    worst_aqi_info = get_worst_aqi_city(all_cities)

    if combined_alerts:
        summary_text = format_zone_summary(combined_alerts)
        if current_summary:
            summary_text = f"Current weather – {current_summary}\n\n" + summary_text
        if worst_aqi_info:
            summary_text += f"\n\n🟤 AQI Alert: {worst_aqi_info}"

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
        
        # Append AQI info to pleasant tweet
        if tweet_text and worst_aqi_info:
            tweet_text += f"\n\nTesting 🟤 AQI Alert: {worst_aqi_info}"

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

    # Always show summary in console
    print("\n📄 Final Weather Summary:")
    if tweet_text:
        print(tweet_text)
    else:
        print("No summary available.")
        
if __name__ == "__main__":
    tweet_weather()
