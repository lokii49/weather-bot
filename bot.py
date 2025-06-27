import os
import requests
import tweepy

# Config
CITY = "Hyderabad"
WEATHER_API_KEY = os.getenv("OWM_API_KEY")
weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={WEATHER_API_KEY}&units=metric"

# Weather fetch
def get_weather():
    try:
        response = requests.get(weather_url)
        data = response.json()

        if response.status_code != 200 or "main" not in data:
            return "⚠️ Unable to fetch weather data."

        temp = data['main']['temp']
        desc = data['weather'][0]['description'].capitalize()
        emoji = "☀️" if "clear" in desc.lower() else "🌧️" if "rain" in desc.lower() else "⛅"
        return f"{emoji} Weather in {CITY} today:\nTemp: {temp}°C\nCondition: {desc}."
    except Exception as e:
        return f"⚠️ Weather fetch error: {e}"

# Tweet once
def tweet_weather():
    try:
        client = tweepy.Client(
            bearer_token=os.getenv("BEARER_TOKEN"),
            consumer_key=os.getenv("API_KEY"),
            consumer_secret=os.getenv("API_SECRET"),
            access_token=os.getenv("ACCESS_TOKEN"),
            access_token_secret=os.getenv("ACCESS_SECRET")
        )
        weather = get_weather()
        response = client.create_tweet(text=weather)
        print("✅ Tweeted!", response.data["id"])
    except Exception as e:
        print("❌ Tweet failed:", e)

# Run once
tweet_weather()
