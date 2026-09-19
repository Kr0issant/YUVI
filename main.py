import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials
from yuvi_bot import YuviBot

load_dotenv()

if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

bot = YuviBot()

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
