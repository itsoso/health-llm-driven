"""Read back a closed meal capture before omitting redundant answer generation.

This module grants no write authority. Capture, consent and nutrition policy run
before it; the executor retains the common completion and persistence guards.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from typing import Any

from sqlalchemy.orm import Session

from app.models.daily_health import DietPhotoAsset, DietRecord
from app.services.utterance_intent_classifier import (
    classify_agent_utterance,
    is_explicit_order_intake,
)


def verified_meal_photo_reply(
    db: Session,
    *,
    message: str,
    user_id: int,
    source_message_id: int,
    record_id: int | None,
    images: list[dict[str, Any]],
    receipts: list[dict[str, Any]],
    cards: list[dict[str, Any]],
) -> str | None:
    """Return a factual acknowledgement only for this turn's complete capture.

    A receipt marker alone is insufficient: its record and every unique input
    image must still be attached to the same owner and originating message.
    Unknown/mixed input or stale evidence leaves the existing model path intact.
    """
    intent = classify_agent_utterance(message)
    if (intent.normalized != "".join(message.split()).lower()
            or not is_explicit_order_intake(intent)
            or type(user_id) is not int or type(source_message_id) is not int
            or user_id <= 0 or source_message_id <= 0
            or type(record_id) is not int or record_id <= 0 or not 1 <= len(images) <= 3
            or len(receipts) != 1 or len(cards) != 1):
        return None
    receipt = receipts[0]
    card = cards[0]
    if not isinstance(receipt, dict) or not isinstance(card, dict):
        return None
    data = card.get("data")
    if (receipt.get("verified") is not True or receipt.get("status") != "verified"
            or receipt.get("action") != "create"
            or receipt.get("operation_id") != f"contextual_meal_photo:{record_id}"
            or receipt.get("resource_type") != "diet_record"
            or receipt.get("resource_id") != str(record_id)
            or card.get("type") != "diet_draft" or not isinstance(data, dict)
            or data.get("recorded") is not True or type(data.get("record_id")) is not int
            or data.get("record_id") != record_id
            or data.get("user_id") != user_id or data.get("media_stage") != "attached"):
        return None
    hashes = set()
    try:
        for image in images:
            if not isinstance(image, dict):
                return None
            encoded = image.get("base64")
            if not isinstance(encoded, str) or not encoded:
                return None
            encoded = encoded.split(",", 1)[-1]
            hashes.add(hashlib.sha256(base64.b64decode(encoded, validate=True)).hexdigest())
    except (ValueError, binascii.Error):
        # Malformed input does not prove a complete saved meal.
        return None
    record = db.query(DietRecord).filter(
        DietRecord.id == record_id, DietRecord.user_id == user_id,
    ).one_or_none()
    if (record is None or receipt.get("date") != record.record_date.isoformat()
            or data.get("record_date") != record.record_date.isoformat()):
        return None
    assets = db.query(DietPhotoAsset).filter(
        DietPhotoAsset.diet_record_id == record_id,
        DietPhotoAsset.user_id == user_id,
    ).all()
    if (len(assets) != len(hashes)
            or {asset.content_sha256 for asset in assets} != hashes
            or any(asset.origin != "chat" or asset.origin_message_id != source_message_id
                   or asset.lifecycle != "attached" or asset.deleted_at is not None
                   or asset.classification != "food" or asset.intent_decision != "auto_record"
                   for asset in assets)
            or not isinstance(data.get("photo_asset_ids"), list)
            or len(data["photo_asset_ids"]) != len(assets)
            or any(not isinstance(asset_id, str) for asset_id in data["photo_asset_ids"])
            or set(data["photo_asset_ids"]) != {asset.id for asset in assets}):
        return None
    return "这餐已记录，照片已关联。营养为图片估算，可在卡片中查看或修正。"
