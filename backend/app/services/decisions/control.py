"""Read the durable switch afresh at each boundary; there is no process cache."""
import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import SessionLocal
from app.models.decision_control import DecisionControl
from app.services.decisions.config import DecisionError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ControlState:
    enabled: bool
    revision: int
    updated_at: datetime


def read_control(db) -> ControlState:
    row = db.get(DecisionControl, 1, populate_existing=True)
    if row is None or type(row.enabled) is not bool or row.revision < 0:
        raise DecisionError("control_unavailable")
    return ControlState(row.enabled, row.revision, row.updated_at)


def runtime_mode() -> str:
    mode = settings.decision_mode
    if mode == "off" or not settings.decision_admin_control_enabled:
        return mode
    try:
        with SessionLocal() as db:
            return mode if read_control(db).enabled else "off"
    except SQLAlchemyError as exc:
        logger.warning("decision_control unavailable error_type=%s", type(exc).__name__)
        raise DecisionError("control_unavailable") from None
