import os
from pyrogram import Client
from dotenv import load_dotenv

load_dotenv()


API_ID = int(os.environ.get("API_ID")) # Telegram API ID
API_HASH = os.environ.get("API_HASH")  # Telegram API Hash

app = Client("my_account", api_id=API_ID, api_hash=API_HASH)


print("Userbot ishga tushishga tayyor...")


app.run()