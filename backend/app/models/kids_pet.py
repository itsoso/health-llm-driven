"""Kids dog pet model."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class KidsPetProfile(Base):
    """儿童模式狗狗空间档案（每个用户一条）"""
    __tablename__ = "kids_pet_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)

    breed_id = Column(String(50), nullable=False)
    breed_name = Column(String(100), nullable=False)
    breed_image = Column(String(255), nullable=True)
    breed_cost = Column(Integer, nullable=False, default=0)
    dog_name = Column(String(50), nullable=False)

    hunger = Column(Integer, nullable=False, default=100)
    happiness = Column(Integer, nullable=False, default=100)
    level = Column(Integer, nullable=False, default=1)
    xp = Column(Integer, nullable=False, default=0)

    food_bags = Column(Integer, nullable=False, default=0)
    has_house = Column(Boolean, nullable=False, default=False)
    has_garden = Column(Boolean, nullable=False, default=False)

    last_decay_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_interaction_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User")
