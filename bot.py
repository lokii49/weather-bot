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

# ✅ Log Twitter authentication
print("🔑 Verifying Twitter credentials...")
try:
    me = TWEEPY_CLIENT.get_me()
    print(f"✅ Authenticated as @{me.data.username}")
except Exception as e:
    print("❌ Twitter authentication failed:", e)

ZONES = {
    "Hyderabad": ["Gachibowli", "Kompally", "LB Nagar"],
    "North Telangana": ["Adilabad", "Nirmal"],
    "South Telangana": ["Mahabubnagar", "Nagarkurnool"],
    "East Telangana": ["Khammam", "Warangal"],
    "West Telangana": ["Sangareddy", "Zaheerabad"],
    "Central Telangana": ["Medchal", "Karimnagar"]
}

IST = pytz.timezone("Asia/Kolkata")

def get_language_mode():
    return random.choice(["telugu", "english"])

def translate_zone(zone):
    telugu_zones = {
        "Hyderabad": "హైదరాబాద్",
        "North Telangana": "ఉత్తర తెలంగాణ",
        "South Telangana": "దక్షిణ తెలంగాణ",
        "East Telangana": "తూర్పు తెలంగాణ",
        "West Telangana": "పడమట తెలంగాణ",
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
        if "rain" in cond or "thunder" in cond or hour.get("precip_mm", 0) > 5:
            alerts.append(f"🌧️ Rain expected in {city} at {t.strftime('%I %p')}")
        elif hour.get("temp_c", 0) >= 40:
            alerts.append(f"🔥 Heatwave in {city} at {t.strftime('%I %p')}")
        elif hour.get("vis_km", 10) < 2:
            alerts.append(f"🌁 Fog risk in {city} at {t.strftime('%I %p')}")
        elif hour.get("wind_kph", 0) > 35:
            alerts.append(f"💨 Strong wind in {city} at {t.strftime('%I %p')}")
    
    if data.get("current", {}).get("air_quality", {}).get("pm2_5", 0) > 60:
        alerts.append(f"🟤 Poor air quality in {city}")

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
    included_zones = set()
    hyderabad_alert = None

    # First, guarantee Hyderabad alert
    for city in ZONES["Hyderabad"]:
        data = fetch_weather(city)
        if not data:
            continue
        city_alerts = detect_alerts(city, data)
        if city_alerts:
            eng = city_alerts[0]
            time_str = eng.split("at")[-1].strip()[:5]
            telugu = translate_alert(eng, city, time_str)
            tel_zone = translate_zone("Hyderabad")

            if lang_mode == "telugu":
                hyderabad_alert = f"📍 {tel_zone}: {telugu}"
            else:
                hyderabad_alert = f"📍 Hyderabad: {eng}"
            break

    # Then, gather alerts from other zones (excluding Hyderabad)
    for zone, cities in ZONES.items():
        if zone == "Hyderabad":
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
                break  # one city per zone

    if not hyderabad_alert and not all_alerts:
        print("✅ No new alerts.")
        return

    summary_items = []
    if hyderabad_alert:
        summary_items.append(hyderabad_alert)
    summary_items.extend(sorted(all_alerts))

    summary = "\n\n".join(summary_items)
    last = load_last_summary()

    if last.get("summary") == summary:
        print("⏳ Alert already posted.")
        print("⚠️ Forcing tweet for debug...")
    else:
        print("✅ New alert detected. Proceeding to tweet.")

    timestamp = datetime.now(IST).strftime('%d %b %I:%M %p')
    if lang_mode == "telugu":
        tweet_text = f"⚠️ వాతావరణ హెచ్చరిక – {timestamp}\n\n{summary}\n\nజాగ్రత్తగా ఉండండి. 🌧️"
    else:
        tweet_text = f"⚠️ Weather Alert – {timestamp}\n\n{summary}\n\nStay safe. 🌧️"

    tweet(tweet_text)

    save_summary({
        "summary": summary,
        "timestamp": datetime.now(IST).isoformat()
    })

if __name__ == "__main__":
    main()
