from dataclasses import dataclass


@dataclass(frozen=True)
class AmountResult:
    wei: int | None
    complete: bool
    reason: str | None = None
