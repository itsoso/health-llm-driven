"""Domain writes for water intake records."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.daily_health import WaterIntake
from app.twin.cache import invalidate_twin
from app.utils.timezone import get_china_now


def create_water_intake(
    db: Session,
    *,
    user_id: int,
    amount_ml: int,
    drink_type: str = "水",
    recorded_at: datetime | None = None,
) -> WaterIntake:
    """Persist one validated water intake and return its durable receipt source."""
    amount = int(amount_ml)
    if amount <= 0 or amount > 5000:
        raise ValueError("amount_ml must be between 1 and 5000")
    now = recorded_at or get_china_now()
    record = WaterIntake(
        user_id=int(user_id),
        record_date=now.date(),
        amount_ml=amount,
        drink_type=str(drink_type or "水"),
        intake_time=now,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    invalidate_twin(int(user_id))
    return record
