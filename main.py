import os
import logging
import asyncio
import ollama
from pyrogram import Client, filters, idle
from dotenv import load_dotenv
from database import init_db, AsyncSessionLocal, GroupMessage

load_dotenv()

logging.basicConfig(level=logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

raw_groups = os.environ.get("ALLOWED_GROUPS", "")
ALLOWED_GROUPS = [int(g_id.strip()) for g_id in raw_groups.split(",") if g_id.strip()]
print(f"⚙️ .env dan yuklangan guruhlar: {ALLOWED_GROUPS}")

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")

app = Client("my_account", api_id=API_ID, api_hash=API_HASH)


async def process_group_message(message):
    group_id = message.chat.id
    group_name = message.chat.title
    text = message.text or message.caption or "[Matnsiz kontent/Media]"


    if group_id not in ALLOWED_GROUPS:
        return

    if message.from_user:
        user_id = message.from_user.id
        username = message.from_user.username or f"User_{user_id}"
    elif message.sender_chat:
        user_id = message.sender_chat.id
        username = message.sender_chat.title or "Kanal_E'loni"
    else:
        user_id = 0
        username = "Tizim"

    async with AsyncSessionLocal() as session:
        try:
            new_msg = GroupMessage(
                user_id=user_id,
                username=username,
                group_id=group_id,
                group_name=group_name,
                message_text=text
            )
            session.add(new_msg)
            await session.commit()
            print(f"💾 BAZAGA YOZILDI: [{group_name}] -> {username}")
        except Exception as e:
            await session.rollback()
            print(f"❌ Postgres xatoligi: {e}")


@app.on_message(filters.group | filters.channel)
async def handle_new_message(client, message):
    await process_group_message(message)


@app.on_edited_message(filters.group | filters.channel)
async def handle_edited_message(client, message):
    await process_group_message(message)


async def main():
    await init_db()
    print("PostgreSQL jadvallari tekshirildi.")

    await app.start()


    print("\n🚀 Userbot JONLI rejimda ishga tushdi. Guruhdagi harakatlarni kuting...")
    await idle()          # pyrogram/kurigram'ning to'xtash signalini kutuvchi tayyor funksiyasi
    await app.stop()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())


