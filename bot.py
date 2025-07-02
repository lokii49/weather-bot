import os, json, random
from datetime import datetime, timedelta
import requests, pytz
from github import Github, InputFileContent
import tweepy
from dotenv import load_dotenv

load_dotenv()

# Load environment variables
WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY")
GIST_TOKEN = os.getenv("GIST_TOKEN")
GIST_ID = os.getenv("GIST_ID")

TWEEPY_CLIENT = tweepy.Client(
    bearer_token=os.getenv("BEARER_TOKEN"),
    consumer_key=os.getenv("API_KEY"),
    consumer_secret=os.getenv("API_SECRET"),
    access_token=os.getenv("ACCESS_TOKEN"),
    access_token_secret=os.getenv("ACCESS_SECRET")
)

print("\U0001F511 Verifying Twitter credentials...")
try:
    me = TWEEPY_CLIENT.get_me()
    print(f"✅ Authenticated as @{me.data.username}")
except Exception as e:
    print("❌ Twitter authentication failed:", e)

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

IST = pytz.timezone("Asia/Kolkata")

def get_language_mode():
    return random.choice(["telugu", "english"])

def translate_zone(zone):
    telugu_zones = {
        "North Hyderabad": "ఉత్తర హైదరాబాద్",
        "South Hyderabad": "దక్షిణ హైదరాబాద్",
        "East Hyderabad": "తూర్పు హైదరాబాద్",
        "West Hyderabad": "పడమటి హైదరాబాద్",
        "Central Hyderabad": "కేంద్ర హైదరాబాద్",
        "North Telangana": "ఉత్తర తెలంగాణ",
        "South Telangana": "దక్షిణ తెలంగాణ",
        "East Telangana": "తూర్పు తెలంగాణ",
        "West Telangana": "పడమటి తెలంగాణ",
        "Central Telangana": "కేంద్ర తెలంగాణ"
    }
    return telugu_zones.get(zone, zone)

def fetch_weather(city):
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

def detect_alerts(city, data):
    now = datetime.now(IST)
    cutoff = now + timedelta(hours=3)
    alerts = []

    for hour in data.get("forecast", {}).get("forecastday", [{}])[0].get("hour", []):
        t = datetime.strptime(hour["time"], "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC).astimezone(IST)
        if not (now <= t <= cutoff):
            continue

        cond = hour.get("condition", {}).get("text", "").lower()
        precip = hour.get("precip_mm", 0)
        temp = hour.get("temp_c", 0)
        vis = hour.get("vis_km", 10)
        wind = hour.get("wind_kph", 0)

        if "heavy rain" in cond or precip > 10:
            alerts.append(f"🌧️ Heavy rain expected in {city} at {t.strftime('%I %p')}")
        elif "moderate rain" in cond or (5 < precip <= 10):
            alerts.append(f"🌦️ Moderate rain expected in {city} at {t.strftime('%I %p')}")
        elif "light rain" in cond or "drizzle" in cond or (0 < precip <= 5):
            alerts.append(f"🌦️ Drizzle in {city} at {t.strftime('%I %p')}")
        elif "thunder" in cond:
            alerts.append(f"⛈️ Thunderstorm expected in {city} at {t.strftime('%I %p')}")
        elif "haze" in cond or "mist" in cond or "smoke" in cond:
            alerts.append(f"🌫️ Hazy conditions in {city} at {t.strftime('%I %p')}")
        elif "fog" in cond or vis < 2:
            alerts.append(f"🌁 Fog risk in {city} at {t.strftime('%I %p')}")
        elif wind > 35:
            alerts.append(f"💨 Strong wind in {city} at {t.strftime('%I %p')}")
        elif temp >= 40:
            alerts.append(f"🔥 Heatwave in {city} at {t.strftime('%I %p')}")

    # Air quality check
    pm2_5 = data.get("current", {}).get("air_quality", {}).get("pm2_5", 0)
    if pm2_5 > 90:
        alerts.append(f"🔴 Very poor air quality in {city}")
    elif pm2_5 > 60:
        alerts.append(f"🟤 Poor air quality in {city}")
    elif pm2_5 > 35:
        alerts.append(f"🟡 Moderate air quality in {city}")

    return alerts

def translate_alert(eng_alert, city, time_label):
    if "rain" in eng_alert.lower():
        return f"🌧️ {city}లో {time_label} గంటలకు వర్షం అవకాశం"
    elif "heatwave" in eng_alert.lower():
        return f"🔥 {city}లో {time_label} గంటలకు తీవ్రమైన వేడి"
    elif "fog" in eng_alert.lower():
        return f"🌁 {city}లో {time_label} గంటలకు మేఘావృతం / పొగమంచు"
    elif "wind" in eng_alert.lower():
        return f"💨 {city}లో {time_label} గంటలకు బలమైన గాలి"
    elif "air quality" in eng_alert.lower():
        return f"🟤 {city}లో కాలుష్య స్థాయి ఎక్కువగా ఉంది"
    else:
        return ""

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
    print("🐦 Posting tweet...")
    try:
        res = TWEEPY_CLIENT.create_tweet(text=text)
        print("✅ Tweeted successfully:", res.data["id"])
    except Exception as e:
        print("❌ Tweet error:", e)

def main():
    print("📡 Checking weather data...")
    lang_mode = get_language_mode()
    print(f"🌐 Randomly selected language: {lang_mode}")

    all_alerts = []

    # ✅ Hyderabad zones
    for zone, cities in HYD_ZONES.items():
        for city in cities:
            data = fetch_weather(city)
            if not data:
                continue
            city_alerts = detect_alerts(city, data)
            if city_alerts:
                eng = city_alerts[0]
                time_str = eng.split("at")[-1].strip()[:5]
                telugu = translate_alert(eng, city, time_str)
                tel_zone = translate_zone(zone)

                if lang_mode == "telugu":
                    all_alerts.append(f"📍 {tel_zone}: {telugu}")
                else:
                    all_alerts.append(f"📍 {zone}: {eng}")
                break

    # ✅ Telangana zones
    for zone, cities in ZONES.items():
        if "Hyderabad" in cities:
            continue
        for city in cities:
            data = fetch_weather(city)
            if not data:
                continue
            city_alerts = detect_alerts(city, data)
            if city_alerts:
                eng = city_alerts[0]
                time_str = eng.split("at")[-1].strip()[:5]
                telugu = translate_alert(eng, city, time_str)
                tel_zone = translate_zone(zone)

                if lang_mode == "telugu":
                    all_alerts.append(f"📍 {tel_zone}: {telugu}")
                else:
                    all_alerts.append(f"📍 {zone}: {eng}")
                break

    if not all_alerts:
        print("✅ No new alerts.")
        return

    summary = "\n\n".join(sorted(all_alerts))
    last = load_last_summary()

    if last.get("summary") == summary:
        print("⏳ Alert already posted.")
    else:
        print("✅ New alert detected. Proceeding to tweet.")

    now_str = datetime.now(IST).strftime('%d %b %I:%M %p')
    if lang_mode == "telugu":
        tweet_text = f"⚠️ వాతావరణ హెచ్చరిక – {now_str}\n\n{summary}\n\nజాగ్రత్తగా ఉండండి. 🌧️"
    else:
        tweet_text = f"⚠️ Weather Alert – {now_str}\n\n{summary}\n\nStay safe. 🌧️"

    tweet(tweet_text)
    save_summary({"summary": summary, "timestamp": datetime.now(IST).isoformat()})

if __name__ == "__main__":
    main()
