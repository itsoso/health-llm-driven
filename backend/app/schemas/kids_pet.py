"""Schemas for kids dog space."""
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


class KidsPetAdoptRequest(BaseModel):
    breed_id: str = Field(..., min_length=1, max_length=50)
    breed_name: str = Field(..., min_length=1, max_length=100)
    breed_cost: int = Field(..., ge=0, le=1000)
    breed_image: Optional[str] = Field(default=None, max_length=255)
    dog_name: str = Field(..., min_length=1, max_length=20)


class KidsPetActionRequest(BaseModel):
    action: Literal["buy_food", "feed", "feed_full", "buy_house", "buy_garden", "return_house", "return_garden", "return_dog"]


class KidsPetState(BaseModel):
    breed_id: str
    breed_name: str
    breed_image: Optional[str] = None
    breed_cost: int = 0
    dog_name: str
    hunger: int
    happiness: int
    level: int
    xp: int
    food_bags: int
    has_house: bool
    has_garden: bool
    last_decay_at: Optional[datetime] = None
    last_interaction_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class KidsPetResponse(BaseModel):
    has_pet: bool
    kids_points: int
    pet: Optional[KidsPetState] = None
    message: Optional[str] = None
