import tweepy
import os
from dotenv import load_dotenv

load_dotenv()

client = tweepy.Client(
    consumer_key=os.getenv("API_KEY"),
    consumer_secret=os.getenv("API_SECRET"),
    access_token=os.getenv("ACCESS_TOKEN"),
    access_token_secret=os.getenv("ACCESS_SECRET")
)

try:
    res = client.create_tweet(text="This is a test tweet from my bot.")
    print("Tweet posted! ID:", res.data["id"])
except Exception as e:
    print("Error:", e)
