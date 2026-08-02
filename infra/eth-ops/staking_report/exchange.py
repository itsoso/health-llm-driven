from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import math
from typing import Any


@dataclass(frozen=True)
class ExchangeRate:
    eth_cny: Decimal
    provider: str
    fetched_at: datetime


def parse_rate(payload: dict[str, Any], provider: str, fetched_at: datetime) -> ExchangeRate:
    value = payload["ethereum"]["cny"]
    if isinstance(value, bool):
        raise ValueError("invalid rate")
    rate = Decimal(str(value))
    if not rate.is_finite() or rate <= 0 or not math.isfinite(float(rate)):
        raise ValueError("invalid rate")
    return ExchangeRate(rate, provider, fetched_at)
