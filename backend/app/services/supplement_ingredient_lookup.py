"""Lookup helpers for reviewed supplement ingredient facts."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.supplement_ingredient import SupplementIngredient

logger = logging.getLogger(__name__)


def normalize_ingredient_name(value: str | None) -> str:
    """Normalize ingredient labels for deterministic local matching."""
    if not value:
        return ""
    lowered = value.strip().lower()
    return re.sub(r"[\s_\-（）()]+", "", lowered)


def find_supplement_ingredient(
    db: Session | None,
    name: str | None,
) -> Optional[SupplementIngredient]:
    """Find an active reviewed ingredient by canonical name or alias.

    The table is intentionally small and curated, so alias matching is done in
    Python for SQLite/Postgres parity instead of relying on JSONB operators.
    """
    target = normalize_ingredient_name(name)
    if db is None or not target:
        return None

    try:
        bind = db.get_bind()
        if bind is not None and not inspect(bind).has_table("supplement_ingredients"):
            return None
        rows = (
            db.query(SupplementIngredient)
            .filter(SupplementIngredient.is_active.is_(True))
            .all()
        )
    except SQLAlchemyError as exc:
        logger.debug("[supplement_ingredient_lookup] lookup failed: %s", exc)
        return None

    for row in rows:
        if normalize_ingredient_name(row.canonical_name) == target:
            return row
    for row in rows:
        aliases = (row.aliases or []) if isinstance(row.aliases, list) else []
        if any(normalize_ingredient_name(label) == target for label in aliases):
            return row
    return None


def resolve_ingredient_ul(
    db: Session | None,
    name: str | None,
) -> Optional[dict[str, Any]]:
    """Return a reviewed UL fact for an ingredient, if present."""
    ingredient = find_supplement_ingredient(db, name)
    if ingredient is None or ingredient.ul_amount is None:
        return None
    return {
        "amount": float(ingredient.ul_amount),
        "unit": ingredient.ul_unit,
        "source": ingredient.source,
        "source_ref": ingredient.source_ref,
        "ingredient_id": ingredient.ingredient_id,
    }
