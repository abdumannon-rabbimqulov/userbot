import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, relationship
from sqlalchemy import Text, String, BigInteger, Boolean, Float, ForeignKey, DateTime, func

load_dotenv()

DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
DB_NAME = os.environ.get("DB_NAME")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class GroupMessage(Base):
    __tablename__ = "group_messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger,nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=True)
    group_id: Mapped[int] = mapped_column(BigInteger,nullable=False)
    group_name: Mapped[str] = mapped_column(String(255), nullable=True)
    message_text: Mapped[str] = mapped_column(Text, nullable=True)


class Region(Base):
    """O'zbekistonning hududlari (viloyat/respublika/shahar)."""
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    is_capital: Mapped[bool] = mapped_column(Boolean, default=False)

    aliases: Mapped[list["RegionAlias"]] = relationship(back_populates="region")


class RegionAlias(Base):
    """Bitta hududning turli yozilish variantlari (Lotin/Kirill, viloyat nomi, shahar nomlari)."""
    __tablename__ = "region_aliases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    alias_text: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)

    region: Mapped["Region"] = relationship(back_populates="aliases")


class VehicleType(Base):
    """Transport turi kategoriyasi (yuk ko'tarish/hajmiga qarab)."""
    __tablename__ = "vehicle_types"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    min_tonna: Mapped[float] = mapped_column(Float, nullable=True)
    max_tonna: Mapped[float] = mapped_column(Float, nullable=True)


class CargoAd(Base):
    """Xom xabardan ajratib olingan strukturaviy yuk e'loni (faqat domestic yo'nalishlar)."""
    __tablename__ = "cargo_ads"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    raw_message_id: Mapped[int] = mapped_column(ForeignKey("group_messages.id"), nullable=False)

    from_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=True)
    from_raw_text: Mapped[str] = mapped_column(String(255), nullable=True)
    to_region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=True)
    to_raw_text: Mapped[str] = mapped_column(String(255), nullable=True)

    vehicle_type_id: Mapped[int] = mapped_column(ForeignKey("vehicle_types.id"), nullable=True)
    vehicle_raw_text: Mapped[str] = mapped_column(String(255), nullable=True)

    weight_tons: Mapped[float] = mapped_column(Float, nullable=True)
    volume_m3: Mapped[float] = mapped_column(Float, nullable=True)

    price_amount: Mapped[float] = mapped_column(Float, nullable=True)
    price_currency: Mapped[str] = mapped_column(String(10), nullable=True)
    is_negotiable: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_method: Mapped[str] = mapped_column(String(50), nullable=True)
    advance_amount: Mapped[float] = mapped_column(Float, nullable=True)
    advance_currency: Mapped[str] = mapped_column(String(10), nullable=True)

    source: Mapped[str] = mapped_column(String(20), nullable=False)  # 'diip' | 'freeform'
    extraction_method: Mapped[str] = mapped_column(String(20), nullable=False)  # 'regex' | 'llm'

    created_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), server_default=func.now())


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)