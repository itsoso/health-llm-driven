"""Prepare dynamic-card descriptors for durable conversation storage."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def cards_for_persistence(cards: list | None) -> list:
    """Remove short-lived private capabilities while retaining durable meaning.

    A signed diet-photo URL is suitable for the current SSE response only. The
    authoritative DietPhotoAsset stores a canonical private key and the Diet
    API re-signs it for later history reads, so conversation metadata must never
    become an alternative storage location for a bearer-like URL.
    """
    durable = deepcopy(cards or [])
    for card in durable:
        if not isinstance(card, dict) or card.get("type") != "diet_draft":
            continue
        data = card.get("data")
        if isinstance(data, dict):
            data.pop("photo_url", None)
    return durable
