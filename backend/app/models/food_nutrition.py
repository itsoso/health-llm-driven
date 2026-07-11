"""Curated food catalog and per-100g nutrition facts."""

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class FoodItem(Base):
    """A reviewed food identity that can be linked from user diet records."""

    __tablename__ = "food_items"

    food_id = Column(String(120), primary_key=True)
    canonical_name = Column(String(200), nullable=False, index=True)
    aliases = Column(JSONB, default=list, nullable=False)
    calibration_names = Column(JSONB, default=list, nullable=False)
    locale = Column(String(20), nullable=False, default="zh-CN")
    source = Column(String(80), nullable=False)
    source_ref = Column(String(200), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class FoodNutrient(Base):
    """Per-100g nutrient profile for a FoodItem."""

    __tablename__ = "food_nutrients"

    food_id = Column(
        String(120),
        ForeignKey("food_items.food_id", ondelete="CASCADE"),
        primary_key=True,
    )
    kcal_per_100g = Column(Float, nullable=True)
    protein_g_per_100g = Column(Float, nullable=True)
    carbs_g_per_100g = Column(Float, nullable=True)
    fat_g_per_100g = Column(Float, nullable=True)
    fiber_g_per_100g = Column(Float, nullable=True)
    source = Column(String(80), nullable=False)
    source_ref = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
