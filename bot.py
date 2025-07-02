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

        if "heavy rain" in cond or precip > 10:
            alerts.append(("🌧️ Heavy rain expected in {} at {}".format(city, t.strftime('%I %p')), "rain"))
        elif "moderate rain" in cond or (5 < precip <= 10):
            alerts.append(("🌦️ Moderate rain expected in {} at {}".format(city, t.strftime('%I %p')), "rain"))
        elif "light rain" in cond or "drizzle" in cond or (0 < precip <= 5):
            alerts.append(("🌦️ Drizzle in {} at {}".format(city, t.strftime('%I %p')), "rain"))
        elif "thunder" in cond:
            alerts.append(("⛈️ Thunderstorm expected in {} at {}".format(city, t.strftime('%I %p')), "rain"))
        # Other alerts not classified as rain are ignored for tweet

    return alerts

def translate_alert(eng_alert, city, time_label):
    if "rain" in eng_alert.lower():
        return f"🌧️ {city}లో {time_label} గంటలకు వర్షం అవకాశం"
    elif "thunder" in eng_alert.lower():
        return f"⛈️ {city}లో {time_label} గంటలకు ఉరుములతో కూడిన వర్షం"
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
    rain_detected = False  # Track if at least one rain alert was found

    # Hyderabad zones
    for zone, cities in HYD_ZONES.items():
        for city in cities:
            data = fetch_weather(city)
            if not data:
                continue
            city_alerts = detect_alerts(city, data)

            # Log all alerts (for future use), but only tweet if rain is present
            rain_alerts = [a for a in city_alerts if a[1] == "rain"]
            if rain_alerts:
                eng = rain_alerts[0][0]
                time_str = eng.split("at")[-1].strip()[:5]
                telugu = translate_alert(eng, city, time_str)
                tel_zone = translate_zone(zone)

                rain_detected = True  # Found a rain alert
                if lang_mode == "telugu":
                    all_alerts.append(f"📍 {tel_zone}: {telugu}")
                else:
                    all_alerts.append(f"📍 {zone}: {eng}")
                break

    # Telangana zones
    for zone, cities in ZONES.items():
        if "Hyderabad" in cities:
            continue
        for city in cities:
            data = fetch_weather(city)
            if not data:
                continue
            city_alerts = detect_alerts(city, data)

            rain_alerts = [a for a in city_alerts if a[1] == "rain"]
            if rain_alerts:
                eng = rain_alerts[0][0]
                time_str = eng.split("at")[-1].strip()[:5]
                telugu = translate_alert(eng, city, time_str)
                tel_zone = translate_zone(zone)

                rain_detected = True
                if lang_mode == "telugu":
                    all_alerts.append(f"📍 {tel_zone}: {telugu}")
                else:
                    all_alerts.append(f"📍 {zone}: {eng}")
                break

    if not rain_detected:
        print("✅ No rain alerts. Skipping tweet.")
        return

    summary = "\n\n".join(sorted(all_alerts))
    last = load_last_summary()

    if last.get("summary") == summary:
        print("⏳ Alert already posted.")
        return

    now_str = datetime.now(IST).strftime('%d %b %I:%M %p')
    if lang_mode == "telugu":
        tweet_text = f"⚠️ వర్ష సూచన – {now_str}\n\n{summary}\n\nజాగ్రత్తగా ఉండండి. 🌧️"
    else:
        tweet_text = f"⚠️ Rain Alert – {now_str}\n\n{summary}\n\nStay safe. 🌧️"

    tweet(tweet_text)
    save_summary({"summary": summary, "timestamp": datetime.now(IST).isoformat()})

if __name__ == "__main__":
    main()
