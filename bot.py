import os
import requests
import tweepy
from dotenv import load_dotenv
from pathlib import Path

# Load env vars
load_dotenv(dotenv_path=Path('.') / '.env')

# Twitter Client Setup
client = tweepy.Client(
    bearer_token=os.getenv("BEARER_TOKEN"),
    consumer_key=os.getenv("API_KEY"),
    consumer_secret=os.getenv("API_SECRET"),
    access_token=os.getenv("ACCESS_TOKEN"),
    access_token_secret=os.getenv("ACCESS_SECRET")
)

# Weather Fetching
def get_weather_summary():
    LOCATIONS = [
        "Hyderabad", "Warangal", "Karimnagar", "Khammam", "Adilabad", "Nizamabad", "Mahbubnagar",
        "Mancherial", "Nalgonda", "Siddipet", "Bodhan", "Jagtial", "Sircilla", "Zaheerabad",
        "Vikarabad", "Kothagudem", "Bhupalpally", "Suryapet", "Bellampalle", "Gadwal", "Miryalaguda",
        "Narayanpet", "Tandur", "Medak", "Yellandu", "Bhongir", "Peddapalli", "Kamareddy", "Koratla"
    ]

    WEATHER_API_KEY = os.getenv("OWM_API_KEY")
    summary = ["🌤️ Telangana Weather Highlights:\n"]

    try:
        for city in LOCATIONS:
            url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
            res = requests.get(url).json()

            if "main" not in res or "weather" not in res:
                continue

            temp = round(res["main"]["temp"])
            desc = res["weather"][0]["description"].capitalize()
            condition = desc.lower()

            # Only include if significant weather
            if "rain" in condition or "storm" in condition or temp > 38 or temp < 15:
                emoji = "🌧️" if "rain" in condition or "storm" in condition else "🔥" if temp > 38 else "❄️"
                summary.append(f"{emoji} {city}: {temp}°C, {desc}")

        if len(summary) == 1:
            return "🌤️ Telangana weather is calm and moderate today. #Telangana #WeatherBot"

        return "\n".join(summary[:10])  # limit to avoid tweet overflow
    except Exception as e:
        return f"⚠️ Error fetching weather: {e}"

# Main execution
if __name__ == "__main__":
    weather_text = get_weather_summary()
    try:
        response = client.create_tweet(text=weather_text)
        print("✅ Tweeted successfully! Tweet ID:", response.data["id"])
    except Exception as e:
        print("❌ Failed to tweet:", e)
