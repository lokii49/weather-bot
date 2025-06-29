import os
import requests
import tweepy
import cohere
from dotenv import load_dotenv
from datetime import datetime
import pytz
from github import Github
GIST_FILE = "last_alert.json"

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

TONE_TEMPLATES = {
    "witty": """
You are a witty Hyderabad local who loves puns.
Write ONE tweet (<280 chars) about the forecast below.

Rules:
- Start with a playful headline, e.g. “Rain, rain, go a‑Hydera‑way ☔ – {date}”
- Mention 2‑4 zone alerts using 📍
- Light humour or wordplay is welcome
- End with a cheeky sign‑off (e.g., “Chai‑me for updates! ☕”)
""",

    "friendly": """
You’re a friendly Indian neighbour sharing today’s weather.
Tweet requirements:
- Warm greeting + date, e.g. “Morning folks!  {date}”
- 2‑4 zone alerts with 📍
- Simple emojis allowed
- End with a caring tip ( “Stay hydrated!” etc.)
""",

    "alert": """
Adopt a crisp, alert‑style tone (like emergency services).
Tweet rules:
- Headline: “⚠️ Weather Alert – {date}”
- Bullet‑like zone alerts (📍)
- No humour, be direct
- Finish with a safety CTA (“Travel only if needed.”)
""",

    "telugu": """
Switch to a casual Telugu‑English mix (“Teluglish”).
Tweet rules:
- Open with a Telugu greeting + date, e.g. “శుభోదయం! {date}”
- Zone alerts with 📍; include at least one Telugu phrase (“వర్షం వస్తోంది!” etc.)
- End with a friendly Telugu sign‑off (“జాగ్రత్త!”)
"""
}

def load_last_alert_from_gist():
    token = os.getenv("GIST_TOKEN")
    gist_id = os.getenv("GIST_ID")
    if not token or not gist_id:
        return {}
    g = Github(token)
    try:
        gist = g.get_gist(gist_id)
        file = gist.files.get(GIST_FILE)
        if file and file.content:
            return json.loads(file.content)
    except Exception as e:
        print("❌ Gist load error:", e)
    return {}

def save_last_alert_to_gist(data):
    token = os.getenv("GIST_TOKEN")
    gist_id = os.getenv("GIST_ID")
    if not token or not gist_id:
        return
    g = Github(token)
    try:
        gist = g.get_gist(gist_id)
        gist.edit(files={GIST_FILE: {"content": json.dumps(data)}})
    except Exception as e:
        print("❌ Gist save error:", e)

def get_tone_of_day(dt=None):
    TONES = list(TONE_TEMPLATES.keys())  # ["witty", "friendly", "alert", "telugu"]
    if dt is None:
        dt = datetime.now(pytz.timezone("Asia/Kolkata"))
    day_number = int(dt.strftime("%j"))
    return TONES[day_number % len(TONES)]

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
        else:
            if hour_only >= start_hour or hour_only < end_hour:
                relevant_hours.append((hour_dt, hour))

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

    aqi_pm25 = data.get("current", {}).get("air_quality", {}).get("pm2_5", 0)
    if aqi_pm25 >= 60 and "pollution" not in seen:
        alerts.append("🟤 Poor air quality – limit outdoor time")
        seen.add("pollution")

    return alerts

def detect_urgent_alerts(zones):
    urgent_alerts = {}

    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    cutoff = now + timedelta(hours=3)

    for zone, cities in zones.items():
        for city in cities:
            data = fetch_weatherapi_forecast(city)
            if not data:
                continue

            hourly = data.get("forecast", {}).get("forecastday", [{}])[0].get("hour", [])
            for h in hourly:
                h_time = datetime.strptime(h["time"], "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC).astimezone(pytz.timezone("Asia/Kolkata"))
                if not (now <= h_time <= cutoff):
                    continue

                text = h.get("condition", {}).get("text", "").lower()
                temp = h.get("temp_c", 0)
                rain = h.get("precip_mm", 0)
                wind = h.get("wind_kph", 0)

                if "thunder" in text or rain > 10:
                    urgent_alerts[zone] = "⛈️ Heavy rain expected soon"
                elif temp >= 42:
                    urgent_alerts[zone] = "🔥 Heatwave alert"
                elif temp <= 10:
                    urgent_alerts[zone] = "❄️ Cold wave likely"
                elif wind >= 40:
                    urgent_alerts[zone] = "💨 Strong winds expected"

                if zone in urgent_alerts:
                    break  # Found one alert for this zone
        if zone in urgent_alerts:
            continue

    return urgent_alerts

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
    return "\n".join(f"📍 {zone}: {alert}" for zone, alert in zone_alerts.items())

def generate_ai_tweet(summary_text, date_str, tone=None):
    if not tone:
        tone = get_tone_of_day()
    prompt_template = TONE_TEMPLATES[tone].format(date=date_str).strip()

    prompt = f"{prompt_template}\n\nForecast summary:\n{summary_text}\n\nTweet:"
    try:
        response = cohere_client.generate(
            model="command-r-plus",
            prompt=prompt,
            max_tokens=280,
            temperature=0.9 if tone in ["witty", "telugu"] else 0.7,
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

    if 5 <= now.hour < 12:
        start_hour, end_hour = 6, 18
    else:
        start_hour, end_hour = 18, 6

    tg_alerts = get_zone_alerts(ZONES, start_hour, end_hour)
    hyd_alerts = get_zone_alerts(HYD_ZONES, start_hour, end_hour)

    combined_alerts = {**tg_alerts, **hyd_alerts}
    if hyd_alerts:
        combined_alerts["Hyderabad"] = next(iter(hyd_alerts.values()))

    summary_text = format_zone_summary(combined_alerts)

    tone_override = os.getenv("FORCE_TONE")  # optional manual override
    tweet_text = generate_ai_tweet(summary_text, date_str, tone=tone_override)

    if tweet_text:
        try:
            print("📢 Tweet content:\n", tweet_text)
            res = client.create_tweet(text=tweet_text)
            print("✅ Weather tweet posted! Tweet ID:", res.data["id"])
        except Exception as e:
            print("❌ Error tweeting:", e)
    else:
        print("❌ Failed to generate tweet.")
        
def is_urgent_weather():
    new_alerts = detect_urgent_alerts({**ZONES, **HYD_ZONES})
    if not new_alerts:
        return False

    last_alert = load_last_alert_from_gist()
    new_summary = format_zone_summary(new_alerts)

    if last_alert.get("summary") == new_summary:
        print("⏳ Same alert as before, skipping tweet.")
        return False

    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    last_time_str = last_alert.get("timestamp")
    if last_time_str:
        last_time = datetime.fromisoformat(last_time_str)
        if now - last_time < timedelta(hours=3):
            print("⏱️ Recent alert tweeted already.")
            return False

    tweet_text = generate_ai_tweet(new_summary, now.strftime("%d %b"), tone="alert")
    if tweet_text:
        try:
            print("📢 Urgent Tweet:\n", tweet_text)
            res = client.create_tweet(text=tweet_text)
            print("✅ Urgent weather tweet posted! Tweet ID:", res.data["id"])
            save_last_alert_to_gist({
                "summary": new_summary,
                "timestamp": now.isoformat()
            })
            return True
        except Exception as e:
            print("❌ Error tweeting urgent alert:", e)
    return False
    
if __name__ == "__main__":
    IST = pytz.timezone("Asia/Kolkata")
    now = datetime.now(IST)

    if 5 <= now.hour < 12 or 18 <= now.hour < 23:
        tweet_weather()
    else:
        if is_urgent_weather():
            print("📡 Urgent alert tweeted.")
        else:
            print("⏸️ No urgent alert, no scheduled tweet.")
