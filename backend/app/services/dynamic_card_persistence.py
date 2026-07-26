"""Prepare dynamic-card descriptors for durable conversation storage."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session


def cards_for_persistence(cards: list | None) -> list:
    """Remove short-lived private capabilities while retaining durable meaning.

    A signed diet-photo URL is suitable for the current SSE response only. The
    authoritative DietPhotoAsset stores a canonical private key and the Diet
    API re-signs it for later history reads, so conversation metadata must never
    become an alternative storage location for a bearer-like URL.
    """
    durable = deepcopy(cards or [])
    for card in durable:
        if not isinstance(card, dict):
            continue
        data = card.get("data")
        if not isinstance(data, dict):
            continue
        if card.get("type") == "diet_draft":
            data.pop("photo_url", None)
        elif card.get("type") == "aigc_media_job":
            result = data.get("result")
            if isinstance(result, dict):
                result.pop("url", None)
    return durable


def message_metas_for_delivery(
    db: Session,
    metas: list[dict[str, Any] | None],
    owner_id: int,
) -> list[dict[str, Any] | None]:
    """Restore short-lived capabilities for owner-scoped conversation delivery.

    Diet cards persist only the authoritative ``photo_asset_id``. Re-hydrate
    all cards in one owner-filtered query so a conversation reload gets fresh
    signed URLs without turning message metadata into capability storage.
    """
    delivered = deepcopy(metas)
    diet_card_data: list[dict[str, Any]] = []
    asset_ids: set[str] = set()

    for meta in delivered:
        if not isinstance(meta, dict):
            continue
        cards = meta.get("cards")
        if not isinstance(cards, list):
            continue
        for card in cards:
            if not isinstance(card, dict) or card.get("type") != "diet_draft":
                continue
            data = card.get("data")
            if not isinstance(data, dict):
                continue
            # Never forward a stale or unverified bearer URL from durable meta.
            data.pop("photo_url", None)
            raw_asset_id = data.get("photo_asset_id")
            if isinstance(raw_asset_id, (str, int)) and not isinstance(raw_asset_id, bool):
                asset_id = str(raw_asset_id).strip()
                if asset_id:
                    diet_card_data.append(data)
                    asset_ids.add(asset_id)

    if not asset_ids:
        return delivered

    from app.models.daily_health import DietPhotoAsset
    from app.utils.diet_image_url import diet_response_image_url

    assets = (
        db.query(DietPhotoAsset)
        .filter(
            DietPhotoAsset.user_id == int(owner_id),
            DietPhotoAsset.id.in_(asset_ids),
            DietPhotoAsset.lifecycle != "deleted",
        )
        .all()
    )
    signed_urls = {
        str(asset.id): diet_response_image_url(asset.storage_key, int(owner_id))
        for asset in assets
    }
    for data in diet_card_data:
        signed_url = signed_urls.get(str(data["photo_asset_id"]).strip())
        if signed_url:
            data["photo_url"] = signed_url
    return delivered
