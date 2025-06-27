import schedule
import time

def job():
    response = client.create_tweet(text=get_weather())
    print("✅ Tweeted!", response.data["id"])

schedule.every().day.at("08:00").do(job)

while True:
    schedule.run_pending()
    time.sleep(60)
