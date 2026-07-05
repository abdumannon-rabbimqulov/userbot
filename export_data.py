import os
import json
import random
import asyncio
from sqlalchemy.future import select
from database import AsyncSessionLocal, GroupMessage

# Fayllar saqlanadigan papka nomi
DATA_DIR = "logistika_data"
os.makedirs(DATA_DIR, exist_ok=True)

# --- MATNNI FILTRLASH LOGIKASI (export_data uchun maxsus) ---
KEYWORDS = [
    "yuk", "yug", "yuq", "fura", "mashina", "yengil", "kuryer", "kurer",
    "toshkent", "samarqand", "vodiydan", "vohaga", "pochta", "рейс", "груз",
    "доставка", "тент", "бортовой", "катта", "кичик", "transport", "logistika"
]

STOP_WORDS = [
    "работа", "qizlar", "pul ishlash", "kino", "obuna", "sotiladi",
    "gruppa", "reklama", "casino", "stavka", "aviator", "salom", "qale"
]


def check_message_usefulness(text: str) -> bool:
    """Matnni kalit so'zlar bo'yicha tahlil qilish"""
    if not text.strip() or len(text) < 5:
        return False
    text_lower = text.lower()
    if any(stop_word in text_lower for stop_word in STOP_WORDS):
        return False
    if any(word in text_lower for word in KEYWORDS):
        return True
    return False


# --- FORMATLASH ---
def format_to_prompt(text: str, is_useful: bool) -> dict:
    """Matnni Llama 3.2 tushunadigan maxsus formatga o'tkazish"""
    answer = "TRUE" if is_useful else "FALSE"

    return {
        "text": f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n"
                f"Siz logistika guruhlaridagi xabarlarni saralovchi AI yordamchisiz. Xabarni o'qib, agar u yuk borligi, mashina/fura kerakligi yoki reyslar haqida bo'lsa FAQAT 'TRUE', boshqa mavzularda bo'lsa FAQAT 'FALSE' deb javob bering.<|eot_id|>"
                f"<|start_header_id|>user<|end_header_id|>\n"
                f"Xabar: {text}\nBu logistika e'lonimi?<|eot_id|>"
                f"<|start_header_id|>assistant<|end_header_id|>\n"
                f"{answer}<|eot_id|>"
    }


async def export_data():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(GroupMessage))
        messages = result.scalars().all()

        if not messages:
            print("⚠️ Bazada hali ma'lumot yo'q!")
            return

        print(f"📦 Bazada jami {len(messages)} ta xabar topildi. Qayta ishlanmoqda...")

        formatted_dataset = []

        for msg in messages:
            if msg.message_text:
                # O'zimizning ichki funksiyani ishlatamiz
                is_useful = check_message_usefulness(msg.message_text)
                json_line = format_to_prompt(msg.message_text, is_useful)
                formatted_dataset.append(json_line)

        random.shuffle(formatted_dataset)

        total = len(formatted_dataset)
        train_end = int(total * 0.8)
        valid_end = int(total * 0.9)

        train_data = formatted_dataset[:train_end]
        valid_data = formatted_dataset[train_end:valid_end]
        test_data = formatted_dataset[valid_end:]

        def save_jsonl(filename, data_list):
            filepath = os.path.join(DATA_DIR, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                for item in data_list:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            print(f"💾 {filename} yaratildi: {len(data_list)} ta qator")

        save_jsonl("train.jsonl", train_data)
        save_jsonl("valid.jsonl", valid_data)
        save_jsonl("test.jsonl", test_data)

        print("\n🎉 AI uchun dataset muvaffaqiyatli tayyorlandi!")


if __name__ == "__main__":
    asyncio.run(export_data())