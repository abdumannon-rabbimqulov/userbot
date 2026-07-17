import re
import asyncio

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.future import select

from database import AsyncSessionLocal, init_db, Region, RegionAlias, VehicleType


def normalize(text: str) -> str:
    """Lotin/Kirill, apostrof va tinish belgilaridan tozalangan qidiruv kaliti."""
    if not text:
        return ""
    text = text.lower()
    text = text.replace("‘", "'").replace("’", "'").replace("ʻ", "'").replace("`", "'")
    text = text.replace("'", "")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# (nomi, poytaxtmi, [aliaslar - viloyat nomi + asosiy shaharlar, Lotin va Kirill]))
REGIONS = [
    ("Toshkent shahri", True, [
        "toshkent", "toshkent shahri", "toshkent poytaxt", "tashkent",
        "ташкент", "ташкент шахар", "г ташкент",
    ]),
    ("Toshkent viloyati", False, [
        "toshkent viloyati", "ташкентская область", "тошкент вилояти",
        "angren", "ангрен", "chirchiq", "чирчик", "olmaliq", "алмалык",
        "bekobod", "бекабад", "ohangaron", "ахангаран", "nazarbek", "назарбек",
    ]),
    ("Andijon", False, [
        "andijon", "andijon viloyati", "андижан", "андижанская область",
    ]),
    ("Namangan", False, [
        "namangan", "namangan viloyati", "наманган", "наманганская область",
    ]),
    ("Farg'ona", False, [
        "fargona", "fargona viloyati", "фергана", "фарғона", "ферганская область",
        "qoqon", "кукон", "коканд", "margilon", "маргилан",
    ]),
    ("Sirdaryo", False, [
        "sirdaryo", "sirdaryo viloyati", "сырдарья", "сырдарьинская область", "сирдарё",
        "guliston", "гулистан",
    ]),
    ("Jizzax", False, [
        "jizzax", "jizzax viloyati", "джизак", "джизакская область", "жиззах",
    ]),
    ("Samarqand", False, [
        "samarqand", "samarqand viloyati", "самарканд", "самаркандская область",
    ]),
    ("Buxoro", False, [
        "buxoro", "buxoro viloyati", "бухара", "бухарская область",
    ]),
    ("Navoiy", False, [
        "navoiy", "navoiy viloyati", "навои", "навоийская область",
    ]),
    ("Qashqadaryo", False, [
        "qashqadaryo", "qashqadaryo viloyati", "кашкадарья", "кашкадарьинская область",
        "qarshi", "карши",
    ]),
    ("Surxondaryo", False, [
        "surxondaryo", "surxondaryo viloyati", "сурхандарья", "сурхандарьинская область",
        "termiz", "термез", "denov", "денов",
    ]),
    ("Xorazm", False, [
        "xorazm", "xorazm viloyati", "хорезм", "хорезмская область", "urganch", "ургенч",
    ]),
    ("Qoraqalpog'iston Respublikasi", False, [
        "qoraqalpogiston", "qoraqalpogiston respublikasi", "каракалпакстан",
        "nukus", "нукус",
    ]),
]

# (nomi, min_tonna, max_tonna, [transport matnidagi kalit so'zlar])
VEHICLE_TYPES = [
    ("Tent Fura", 18, 24, ["tent fura", "тент фура"]),
    ("Fura (paravoz)", 18, 24, ["paravoz", "паравоз"]),
    ("Muzlatgich", 15, 22, ["muzlatgich", "реф фура", "рефрижератор", "реф"]),
    ("Izotermal fura", 15, 22, ["izotermal", "изотерм"]),
    ("Isuzu 10", 8, 12, ["isuzu 10", "изузу 10", "исузу 10"]),
    ("Isuzu 5", 3, 6, ["isuzu 5", "изузу 5", "исузу 5"]),
    ("Furgon", 2, 8, ["furgon", "фургон"]),
    ("Platforma", 10, 20, ["platforma", "платформа", "bortovoy", "бортовой", "борт"]),
    ("Tral", 20, 60, ["tral", "трал"]),
    ("Konteynervoz", 20, 40, ["konteyner", "контейнеровоз", "контейнер"]),
    ("Bongo/Labo (kichik)", 0.5, 2, ["bongo", "labo", "damas", "лабо", "дамас", "бонго"]),
    ("Avtovoz", 5, 20, ["avtovoz", "автовоз"]),
    ("Boshqa", None, None, ["boshqa"]),
]


async def seed():
    await init_db()
    async with AsyncSessionLocal() as session:
        for name, is_capital, aliases in REGIONS:
            stmt = pg_insert(Region).values(name=name, is_capital=is_capital).on_conflict_do_nothing(index_elements=["name"])
            await session.execute(stmt)
        await session.commit()

        result = await session.execute(select(Region))
        region_by_name = {r.name: r.id for r in result.scalars().all()}

        for name, _is_capital, aliases in REGIONS:
            region_id = region_by_name[name]
            for alias in aliases + [name]:
                stmt = pg_insert(RegionAlias).values(
                    region_id=region_id, alias_text=normalize(alias)
                ).on_conflict_do_nothing(index_elements=["alias_text"])
                await session.execute(stmt)
        await session.commit()

        for name, min_t, max_t, _keywords in VEHICLE_TYPES:
            stmt = pg_insert(VehicleType).values(
                name=name, min_tonna=min_t, max_tonna=max_t
            ).on_conflict_do_nothing(index_elements=["name"])
            await session.execute(stmt)
        await session.commit()

        n_regions = len((await session.execute(select(Region))).scalars().all())
        n_aliases = len((await session.execute(select(RegionAlias))).scalars().all())
        n_vehicles = len((await session.execute(select(VehicleType))).scalars().all())
        print(f"✅ Regions: {n_regions}, RegionAliases: {n_aliases}, VehicleTypes: {n_vehicles}")


if __name__ == "__main__":
    asyncio.run(seed())
