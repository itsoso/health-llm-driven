from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class CollectionResult:
    value: Any
    complete: bool
    error: str | None = None


def collect_safely(name: str, operation: Callable[[], Any]) -> CollectionResult:
    try:
        return CollectionResult(operation(), True)
    except Exception as exc:
        return CollectionResult(None, False, f"{name}: {exc}")
