import re
import json
import asyncio

import ollama
from sqlalchemy.future import select

from database import AsyncSessionLocal, GroupMessage, RegionAlias, VehicleType, CargoAd
from seed_reference_data import normalize, VEHICLE_TYPES

OLLAMA_MODEL = "qwen2.5:7b"

UZ_FLAG = "🇺🇿"
FLAG_PATTERN = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")
ROUTE_RE = re.compile(
    rf"({FLAG_PATTERN.pattern})\s*([^\n→]+?)\s*→\s*({FLAG_PATTERN.pattern})\s*([^\n]+)"
)
WEIGHT_RE = re.compile(
    r"VAZNI:\s*([\d]+(?:[.,]\d+)?)\s*tonna(?:\s+([\d]+(?:[.,]\d+)?)\s*m)?", re.IGNORECASE
)
TRANSPORT_RE = re.compile(r"TRANSPORT:\s*(.+)")
TOLOV_RE = re.compile(r"TO.?LOV:\s*(.+)", re.IGNORECASE)
PRICE_RE = re.compile(r"([\d]+(?:[.,]\d+)?)\s*(USD|UZS|EUR|RUB|KZT)", re.IGNORECASE)
ADVANCE_RE = re.compile(r"Avans\s*([\d]+(?:[.,]\d+)?)\s*(USD|UZS|EUR|RUB|KZT)", re.IGNORECASE)
PAYMENT_KEYWORDS = ["Naqd", "Nasiya", "Aralash", "Plastik"]

EXTRACTION_SYSTEM_PROMPT = """Siz O'zbekiston ichidagi yuk tashish e'lonlaridan strukturaviy ma'lumot ajratib oluvchi yordamchisiz.
Foydalanuvchi xabarini o'qib, FAQAT quyidagi JSON formatda javob bering (boshqa hech qanday matn yozmang):
{
  "is_domestic": true yoki false,   // ikkala tomon (jo'natuvchi va qabul qiluvchi) ham O'zbekiston hududimi
  "from_region": "matn yoki null",  // qayerdan (viloyat/shahar nomi, xabardagi original yozilishi)
  "to_region": "matn yoki null",    // qayerga
  "vehicle_raw": "matn yoki null",  // transport turi (masalan: Tent fura, Isuzu 5, Kamaz, Bortovoy)
  "weight_tons": number yoki null,
  "volume_m3": number yoki null,
  "price_amount": number yoki null,
  "price_currency": "UZS" yoki "USD" yoki null,
  "is_negotiable": true yoki false,
  "payment_method": "matn yoki null",
  "advance_amount": number yoki null,
  "advance_currency": "matn yoki null"
}
Misol:
Xabar: "НАМАНГАН >> НУКУС. Стул 15 дона. Тент керак. Нарх 1500000 сум"
Javob: {"is_domestic": true, "from_region": "Наманган", "to_region": "Нукус", "vehicle_raw": "Тент", "weight_tons": null, "volume_m3": null, "price_amount": 1500000, "price_currency": "UZS", "is_negotiable": false, "payment_method": null, "advance_amount": null, "advance_currency": null}

Agar xabar yuk tashish e'loni bo'lmasa, yo'nalish aniq bo'lmasa, yoki tomonlardan biri O'zbekistondan tashqarida bo'lsa - "is_domestic": false qiling.
"""


def find_route(text: str):
    m = ROUTE_RE.search(text)
    if not m:
        return None
    return m.groups()  # flag1, region1_raw, flag2, region2_raw


def parse_diip_fields(text: str) -> dict:
    weight_m = WEIGHT_RE.search(text)
    transport_m = TRANSPORT_RE.search(text)
    tolov_m = TOLOV_RE.search(text)

    weight_tons = volume_m3 = None
    if weight_m:
        weight_tons = float(weight_m.group(1).replace(",", "."))
        if weight_m.group(2):
            volume_m3 = float(weight_m.group(2).replace(",", "."))

    vehicle_raw = transport_m.group(1).strip() if transport_m else None

    price_amount = price_currency = payment_method = None
    advance_amount = advance_currency = None
    is_negotiable = False

    if tolov_m:
        line = tolov_m.group(1).strip()
        if "kelishiladi" in line.lower():
            is_negotiable = True
        price_match = PRICE_RE.search(line)
        if price_match:
            price_amount = float(price_match.group(1).replace(",", "."))
            price_currency = price_match.group(2).upper()
        for kw in PAYMENT_KEYWORDS:
            if kw.lower() in line.lower():
                payment_method = kw
                break
        advance_m = ADVANCE_RE.search(line)
        if advance_m:
            advance_amount = float(advance_m.group(1).replace(",", "."))
            advance_currency = advance_m.group(2).upper()

    return {
        "vehicle_raw": vehicle_raw,
        "weight_tons": weight_tons,
        "volume_m3": volume_m3,
        "price_amount": price_amount,
        "price_currency": price_currency,
        "is_negotiable": is_negotiable,
        "payment_method": payment_method,
        "advance_amount": advance_amount,
        "advance_currency": advance_currency,
    }


def has_foreign_flag(text: str) -> bool:
    return any(f != UZ_FLAG for f in FLAG_PATTERN.findall(text))


def has_uzbek_region_mentions(text: str, alias_to_region_id: dict, min_distinct: int = 2) -> bool:
    norm = normalize(text)
    found = set()
    for alias, rid in alias_to_region_id.items():
        if alias and alias in norm:
            found.add(rid)
            if len(found) >= min_distinct:
                return True
    return False


def scan_regions_in_text(text: str, alias_to_region_id: dict) -> list:
    """Matndagi barcha ma'lum hudud aliaslarini birinchi uchragan tartibda qaytaradi."""
    norm = normalize(text)
    hits = []
    for alias, rid in alias_to_region_id.items():
        if not alias:
            continue
        idx = norm.find(alias)
        if idx != -1:
            hits.append((idx, rid, len(alias)))
    hits.sort(key=lambda h: (h[0], -h[2]))
    seen_ids, ordered = set(), []
    for _idx, rid, _ln in hits:
        if rid not in seen_ids:
            seen_ids.add(rid)
            ordered.append(rid)
    return ordered


def match_region(raw_text, alias_to_region_id: dict):
    if not raw_text:
        return None
    norm = normalize(raw_text)
    if not norm:
        return None
    if norm in alias_to_region_id:
        return alias_to_region_id[norm]
    best_id, best_len = None, 0
    for alias, rid in alias_to_region_id.items():
        if alias and alias in norm and len(alias) > best_len:
            best_id, best_len = rid, len(alias)
    return best_id


def match_vehicle(raw_text, keyword_pairs: list):
    if not raw_text:
        return None
    norm = normalize(raw_text)
    for kw, vt_id in keyword_pairs:
        if kw and kw in norm:
            return vt_id
    return None


def call_ollama_extract(text: str):
    try:
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            format="json",
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"Xabar:\n{text}"},
            ],
        )
        data = json.loads(resp["message"]["content"])
    except Exception as e:
        print(f"⚠️ Ollama xatolik: {e}")
        return None

    return {
        "is_domestic": bool(data.get("is_domestic", False)),
        "from_raw": data.get("from_region"),
        "to_raw": data.get("to_region"),
        "vehicle_raw": data.get("vehicle_raw"),
        "weight_tons": data.get("weight_tons"),
        "volume_m3": data.get("volume_m3"),
        "price_amount": data.get("price_amount"),
        "price_currency": data.get("price_currency"),
        "is_negotiable": bool(data.get("is_negotiable", False)),
        "payment_method": data.get("payment_method"),
        "advance_amount": data.get("advance_amount"),
        "advance_currency": data.get("advance_currency"),
    }


async def load_lookups(session):
    region_result = await session.execute(select(RegionAlias))
    alias_to_region_id = {ra.alias_text: ra.region_id for ra in region_result.scalars().all()}

    vt_result = await session.execute(select(VehicleType))
    vehicle_name_to_id = {vt.name: vt.id for vt in vt_result.scalars().all()}

    keyword_pairs = []
    for name, _min_t, _max_t, keywords in VEHICLE_TYPES:
        vt_id = vehicle_name_to_id.get(name)
        if vt_id is None:
            continue
        for kw in keywords:
            keyword_pairs.append((normalize(kw), vt_id))
    keyword_pairs.sort(key=lambda pair: -len(pair[0]))

    return alias_to_region_id, keyword_pairs


async def main():
    async with AsyncSessionLocal() as session:
        alias_to_region_id, keyword_pairs = await load_lookups(session)
        if not alias_to_region_id or not keyword_pairs:
            print("⚠️ Regions/VehicleTypes bazasi bo'sh. Avval `python seed_reference_data.py`ni ishga tushiring.")
            return

        result = await session.execute(select(GroupMessage))
        messages = result.scalars().all()
        print(f"📦 Jami xabarlar: {len(messages)}")

        stats = {
            "diip_total": 0, "diip_domestic": 0, "diip_intl_skipped": 0, "diip_unparsed": 0,
            "freeform_total": 0, "freeform_prefiltered_out": 0,
            "freeform_llm_ok": 0, "freeform_llm_failed": 0, "freeform_not_domestic": 0,
            "region_unmapped": 0, "vehicle_unmapped": 0,
            "priced": 0, "negotiable": 0,
        }

        rows_to_insert = []

        for msg in messages:
            text = msg.message_text
            if not text:
                continue

            if "diip.uz" in text:
                stats["diip_total"] += 1
                route = find_route(text)
                if route is None:
                    stats["diip_unparsed"] += 1
                    continue
                flag1, region1_raw, flag2, region2_raw = route
                if flag1 != UZ_FLAG or flag2 != UZ_FLAG:
                    stats["diip_intl_skipped"] += 1
                    continue
                stats["diip_domestic"] += 1
                parsed = parse_diip_fields(text)
                parsed["from_raw"] = region1_raw.strip()
                parsed["to_raw"] = region2_raw.strip()
                source, extraction_method = "diip", "regex"
            else:
                stats["freeform_total"] += 1
                if has_foreign_flag(text) or not has_uzbek_region_mentions(text, alias_to_region_id, min_distinct=2):
                    stats["freeform_prefiltered_out"] += 1
                    continue
                parsed = call_ollama_extract(text)
                if parsed is None:
                    stats["freeform_llm_failed"] += 1
                    continue
                if not parsed["is_domestic"] or not parsed["from_raw"] or not parsed["to_raw"]:
                    stats["freeform_not_domestic"] += 1
                    continue
                stats["freeform_llm_ok"] += 1
                source, extraction_method = "freeform", "llm"

            from_region_id = match_region(parsed["from_raw"], alias_to_region_id)
            to_region_id = match_region(parsed["to_raw"], alias_to_region_id)

            if from_region_id is None or to_region_id is None:
                # LLM ba'zan hudud nomini buzib qaytaradi yoki xalqaro yo'nalishni domestic deb
                # noto'g'ri belgilaydi - asl xabar matnidan mustaqil tekshirib ko'ramiz.
                # Faqat ANIQ va BITTA nomzod topilganda to'ldiramiz - bir nechta yo'nalish
                # birlashtirilgan (bundle) xabarlarda noto'g'ri juftlik hosil qilmaslik uchun.
                distinct_in_text = scan_regions_in_text(text, alias_to_region_id)
                if from_region_id is None and to_region_id is None:
                    if len(distinct_in_text) == 2:
                        from_region_id, to_region_id = distinct_in_text[0], distinct_in_text[1]
                elif from_region_id is None:
                    others = [rid for rid in distinct_in_text if rid != to_region_id]
                    if len(others) == 1:
                        from_region_id = others[0]
                elif to_region_id is None:
                    others = [rid for rid in distinct_in_text if rid != from_region_id]
                    if len(others) == 1:
                        to_region_id = others[0]

            if from_region_id is None or to_region_id is None or from_region_id == to_region_id:
                stats["region_unmapped"] += 1
                if source == "freeform":
                    # Hudud aniqlanmasa (ko'pincha xalqaro yo'nalish LLM tomonidan xato
                    # domestic deb belgilangani uchun), qatorni bazaga yozmaymiz.
                    stats["freeform_dropped_unresolved_region"] = stats.get("freeform_dropped_unresolved_region", 0) + 1
                    continue

            vehicle_type_id = match_vehicle(parsed["vehicle_raw"], keyword_pairs)
            if vehicle_type_id is None:
                stats["vehicle_unmapped"] += 1

            if parsed.get("price_amount"):
                stats["priced"] += 1
            if parsed.get("is_negotiable"):
                stats["negotiable"] += 1

            rows_to_insert.append(CargoAd(
                raw_message_id=msg.id,
                from_region_id=from_region_id,
                from_raw_text=parsed["from_raw"],
                to_region_id=to_region_id,
                to_raw_text=parsed["to_raw"],
                vehicle_type_id=vehicle_type_id,
                vehicle_raw_text=parsed["vehicle_raw"],
                weight_tons=parsed.get("weight_tons"),
                volume_m3=parsed.get("volume_m3"),
                price_amount=parsed.get("price_amount"),
                price_currency=parsed.get("price_currency"),
                is_negotiable=bool(parsed.get("is_negotiable")),
                payment_method=parsed.get("payment_method"),
                advance_amount=parsed.get("advance_amount"),
                advance_currency=parsed.get("advance_currency"),
                source=source,
                extraction_method=extraction_method,
            ))

        session.add_all(rows_to_insert)
        await session.commit()

        print("\n📊 Natijalar:")
        print(f"  Bazaga yozildi: {len(rows_to_insert)}")
        for k, v in stats.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
