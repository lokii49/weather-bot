import os, json, random
from datetime import datetime, timedelta
import requests, pytz
from github import Github, InputFileContent
import tweepy
from dotenv import load_dotenv

load_dotenv()

# Load environment variables
WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")
GIST_TOKEN = os.getenv("GIST_TOKEN")
GIST_ID = os.getenv("GIST_ID")

TWEEPY_CLIENT = tweepy.Client(
    bearer_token=os.getenv("BEARER_TOKEN"),
    consumer_key=os.getenv("API_KEY"),
    consumer_secret=os.getenv("API_SECRET"),
    access_token=os.getenv("ACCESS_TOKEN"),
    access_token_secret=os.getenv("ACCESS_SECRET")
)

IST = pytz.timezone("Asia/Kolkata")

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

def fetch_weatherapi(city):
    url = "http://api.weatherapi.com/v1/forecast.json"
    params = {
        "key": WEATHERAPI_KEY,
        "q": f"{city}, Telangana",
        "days": 1,
        "alerts": "yes",
        "aqi": "yes"
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        return res.json() if res.status_code == 200 else None
    except:
        return None

def fetch_openweather(city):
    try:
        geocode_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city},Telangana,IN&limit=1&appid={OPENWEATHER_KEY}"
        geo_res = requests.get(geocode_url).json()
        if not geo_res:
            return None
        lat, lon = geo_res[0]['lat'], geo_res[0]['lon']

        weather_url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=metric&appid={OPENWEATHER_KEY}"
        res = requests.get(weather_url)
        return res.json() if res.status_code == 200 else None
    except:
        return None

def detect_alerts(city):
    wapi = fetch_weatherapi(city)
    owm = fetch_openweather(city)
    if not wapi or not owm:
        return []

    alerts = []
    now = datetime.now(IST)
    cutoff = now + timedelta(hours=9)

    for hour in wapi.get("forecast", {}).get("forecastday", [{}])[0].get("hour", []):
        t = datetime.strptime(hour["time"], "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC).astimezone(IST)
        if not (now <= t <= cutoff):
            continue

        cond = hour.get("condition", {}).get("text", "").lower()
        precip = hour.get("precip_mm", 0)
        prob = hour.get("chance_of_rain", 0)  # ✅ Rain probability
        temp = hour.get("temp_c", 0)
        vis = hour.get("vis_km", 10)
        wind = hour.get("wind_kph", 0)
        time_label = t.strftime('%I %p')

        if "heavy rain" in cond or precip > 10:
            alerts.append((f"🌧️ Heavy rain expected in {city} at {time_label} ({prob}% chance)", "rain"))
        elif "moderate rain" in cond or (5 < precip <= 10):
            alerts.append((f"🌦️ Moderate rain expected in {city} at {time_label} ({prob}% chance)", "rain"))
        elif "light rain" in cond or "drizzle" in cond or (0 < precip <= 5):
            alerts.append((f"🌦️ Drizzle in {city} at {time_label} ({prob}% chance)", "rain"))
        elif "thunder" in cond:
            alerts.append((f"⛈️ Thunderstorm expected in {city} at {time_label} ({prob}% chance)", "rain"))
        elif "haze" in cond or "mist" in cond or "smoke" in cond:
            alerts.append((f"🌫️ Hazy conditions in {city} at {time_label}", "fog"))
        elif "fog" in cond or vis < 2:
            alerts.append((f"🌁 Fog risk in {city} at {time_label}", "fog"))
        elif wind > 35:
            alerts.append((f"💨 Strong wind in {city} at {time_label}", "wind"))
        elif temp >= 40:
            alerts.append((f"🔥 Heatwave in {city} at {time_label}", "heat"))

    return alerts

def load_last_summary():
    if not GIST_TOKEN or not GIST_ID:
        return {}
    g = Github(GIST_TOKEN)
    try:
        gist = g.get_gist(GIST_ID)
        file = gist.files.get("last_alert.json")
        return json.loads(file.content) if file and file.content else {}
    except:
        return {}

def save_summary(data):
    if not GIST_TOKEN or not GIST_ID:
        return
    g = Github(GIST_TOKEN)
    gist = g.get_gist(GIST_ID)
    gist.edit(files={"last_alert.json": InputFileContent(json.dumps(data))})

def tweet(text):
    try:
        res = TWEEPY_CLIENT.create_tweet(text=text)
        print("✅ Tweeted successfully:", res.data["id"])
    except Exception as e:
        print("❌ Tweet error:", e)

def main():
    print("📡 Checking weather data...")
    all_alerts = []
    has_rain = False

    all_zones = list(HYD_ZONES.items()) + list(ZONES.items())
    for zone, cities in all_zones:
        for city in cities:
            city_alerts = detect_alerts(city)
            if city_alerts:
                eng, category = city_alerts[0]

                if category == "rain":
                    has_rain = True

                all_alerts.append(f"📍 {zone}: {eng}")
                break

    if not all_alerts:
        print("✅ No alerts found. Skipping tweet.")
        return

    summary = "\n\n".join(sorted(all_alerts))
    last = load_last_summary()

    if last.get("summary") == summary:
        print("⏳ Alert already posted.")
        return

    now_str = datetime.now(IST).strftime('%d %b %I:%M %p')
    header = "⚠️ Rain Alert" if has_rain else "⚠️ Weather Alert"
    tweet_text = f"{header} – {now_str}\n\n{summary}\n\nStay safe. 🌧️"

    tweet(tweet_text)
    save_summary({"summary": summary, "timestamp": datetime.now(IST).isoformat()})

if __name__ == "__main__":
    main()
