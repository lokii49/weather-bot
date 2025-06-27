import os
import requests
import tweepy
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env
load_dotenv(dotenv_path=Path('.') / '.env')

# === Configuration ===
CITY = "Hyderabad"
WEATHER_API_KEY = os.getenv("OWM_API_KEY")

# Build OpenWeatherMap URL
weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={WEATHER_API_KEY}&units=metric"

# === Weather Fetcher ===
def get_weather():
    response = requests.get(weather_url)
    data = response.json()

    if response.status_code != 200 or "main" not in data:
        return "⚠️ Unable to fetch weather data right now."

    temp = data['main']['temp']
    desc = data['weather'][0]['description'].capitalize()
    return f"🌤️ Weather in {CITY} today:\nTemperature: {temp}°C\nCondition: {desc}.\n#weather #bot"

# === Twitter API v2 client ===
client = tweepy.Client(
    bearer_token=os.getenv("BEARER_TOKEN"),
    consumer_key=os.getenv("API_KEY"),
    consumer_secret=os.getenv("API_SECRET"),
    access_token=os.getenv("ACCESS_TOKEN"),
    access_token_secret=os.getenv("ACCESS_SECRET")
)

# === Post weather tweet ===
weather_text = get_weather()
response = client.create_tweet(text=weather_text)
print("✅ Tweeted successfully! Tweet ID:", response.data['id'])
