import os
import asyncio
from pyrogram import Client,filters
from dotenv import load_dotenv
from database import init_db, AsyncSessionLocal, GroupMessage


load_dotenv()


raw_groups = os.environ.get("ALLOWED_GROUPS", "")

ALLOWED_GROUPS = [int(g_id.strip()) for g_id in raw_groups.split(",") if g_id.strip()]

print(f"Kuzatilayotgan guruhlar ro'yxati: {ALLOWED_GROUPS}")


API_ID = int(os.environ.get("API_ID")) # Telegram API ID
API_HASH = os.environ.get("API_HASH")  # Telegram API Hash



app = Client("my_account", api_id=API_ID, api_hash=API_HASH)


@app.on_message(filters.group)
async def catch_and_save_messages(client, message):
    group_id = message.chat.id

    # 1-Filtr: Xabar kelgan guruh biz ruxsat bergan (.env dagi) guruhlar ro'yxatida bormi?
    if group_id not in ALLOWED_GROUPS:
        return

    if message.from_user:
        user_id = message.from_user.id
        username = message.from_user.username or f"User_{user_id}"
    elif message.sender_chat:  # Agar xabar kanal nomidan kelgan bo'lsa (Linked Chat)
        user_id = message.sender_chat.id
        username = message.sender_chat.title or "Kanal_E'loni"
    else:
        user_id = 0
        username = "Noma'lum_Yuboruvchi"

    group_name = message.chat.title

    text = message.text or message.caption or "[Media / Rasm / Fayl]"


    # 2. ASINXRON ma'lumotlar bazasiga (PostgreSQL) saqlash
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
            print(f"✅ Saqlandi: [{group_name}] -> {username}: {text[:30]}...")
        except Exception as e:
            await session.rollback()
            print(f"❌ Postgres'ga yozishda xatolik: {e}")
            return

# --- ISHGA TUSHIRISH LOGIKASI ---

async def main():
    # Bot yoqilishidan oldin PostgreSQL jadvallarini tekshiradi/yaratadi
    await init_db()
    print("PostgreSQL jadvallari tekshirildi.")

    # Userbotni ishga tushiramiz
    await app.start()
    print("Userbot muvaffaqiyatli ishga tushdi va guruhlarni kuzatmoqda...")

    # Dastur doimiy ishlab turishi uchun kutish rejimi
    await asyncio.Event().wait()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())