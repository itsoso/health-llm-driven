"""Reviewed supplement ingredient facts used by safety guardrails."""

from sqlalchemy import Boolean, Column, DateTime, Float, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class SupplementIngredient(Base):
    """A reviewed supplement ingredient identity with optional UL fact."""

    __tablename__ = "supplement_ingredients"

    ingredient_id = Column(String(120), primary_key=True)
    canonical_name = Column(String(200), nullable=False, index=True)
    aliases = Column(JSONB, default=list, nullable=False)
    ul_amount = Column(Float, nullable=True)
    ul_unit = Column(String(40), nullable=True)
    source = Column(String(80), nullable=False)
    source_ref = Column(String(200), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
