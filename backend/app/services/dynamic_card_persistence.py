"""Prepare dynamic-card descriptors for durable conversation storage."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import and_, or_
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
            data.pop("photo_urls", None)
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
    _refresh_record_quality_edits(db, delivered, owner_id)
    diet_card_data: list[
        tuple[dict[str, Any], dict[str, Any], list[str], int | None, bool]
    ] = []
    asset_ids: set[str] = set()
    capture_origin_message_ids: set[int] = set()

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
            data.pop("photo_urls", None)
            raw_asset_ids = data.get("photo_asset_ids")
            if not isinstance(raw_asset_ids, list):
                raw_asset_ids = [data.get("photo_asset_id")]
            ordered_ids: list[str] = []
            seen_ids: set[str] = set()
            for raw_asset_id in raw_asset_ids:
                if not isinstance(raw_asset_id, (str, int)) or isinstance(raw_asset_id, bool):
                    continue
                asset_id = str(raw_asset_id).strip()
                if asset_id and asset_id not in seen_ids:
                    seen_ids.add(asset_id)
                    ordered_ids.append(asset_id)
                    asset_ids.add(asset_id)
            raw_capture_session_id = data.get("capture_session_id")
            capture_origin_message_id = _capture_origin_message_id(
                raw_capture_session_id,
            )
            capture_session_invalid = (
                raw_capture_session_id is not None
                and capture_origin_message_id is None
            )
            if capture_origin_message_id is not None:
                capture_origin_message_ids.add(capture_origin_message_id)
            if ordered_ids or raw_capture_session_id is not None:
                diet_card_data.append((
                    card,
                    data,
                    ordered_ids,
                    capture_origin_message_id,
                    capture_session_invalid,
                ))

    if not asset_ids and not capture_origin_message_ids:
        return delivered

    from app.models.daily_health import DietPhotoAsset
    from app.utils.diet_image_url import diet_response_image_url

    identity_filters = []
    if asset_ids:
        identity_filters.append(DietPhotoAsset.id.in_(asset_ids))
    if capture_origin_message_ids:
        identity_filters.append(and_(
            DietPhotoAsset.origin == "chat",
            DietPhotoAsset.origin_message_id.in_(capture_origin_message_ids),
        ))
    assets = (
        db.query(DietPhotoAsset)
        .filter(
            DietPhotoAsset.user_id == int(owner_id),
            DietPhotoAsset.lifecycle != "deleted",
            or_(*identity_filters),
        )
        .order_by(
            DietPhotoAsset.origin_message_id.asc(),
            DietPhotoAsset.ordinal.asc(),
            DietPhotoAsset.created_at.asc(),
            DietPhotoAsset.id.asc(),
        )
        .all()
    )
    assets_by_id = {str(asset.id): asset for asset in assets}
    assets_by_capture: dict[int, list[Any]] = {}
    for asset in assets:
        if asset.origin == "chat" and asset.origin_message_id is not None:
            assets_by_capture.setdefault(
                int(asset.origin_message_id),
                [],
            ).append(asset)

    for (
        card,
        data,
        ordered_ids,
        capture_origin_message_id,
        capture_session_invalid,
    ) in diet_card_data:
        raw_record_id = data.get("record_id")
        expected_record_id: int | None = None
        if isinstance(raw_record_id, int) and not isinstance(raw_record_id, bool):
            expected_record_id = raw_record_id
        elif isinstance(raw_record_id, str) and raw_record_id.strip().isdigit():
            expected_record_id = int(raw_record_id.strip())
        expected_draft_token = str(data.get("photo_draft_token") or "").strip() or None

        parent_valid_assets = []
        if capture_session_invalid:
            candidate_assets = []
        elif capture_origin_message_id is not None:
            # The capture session is the durable card identity. It recovers
            # photos added after the card was persisted and follows the
            # authoritative draft -> record parent transition.
            candidate_assets = assets_by_capture.get(
                capture_origin_message_id,
                [],
            )
        else:
            candidate_assets = [
                assets_by_id[asset_id]
                for asset_id in ordered_ids
                if asset_id in assets_by_id
            ]
        unavailable_basis = max(len(candidate_assets), len(ordered_ids))
        for asset in candidate_assets:
            if capture_origin_message_id is None:
                if (
                    expected_record_id is not None
                    and asset.diet_record_id != expected_record_id
                ):
                    continue
                if expected_draft_token is not None and not (
                    asset.photo_draft_token == expected_draft_token
                    or (
                        asset.photo_draft_token is None
                        and asset.diet_record_id is not None
                        and asset.origin == "chat"
                        and asset.origin_message_id is not None
                    )
                ):
                    continue
            if bool(asset.diet_record_id) == bool(asset.photo_draft_token):
                continue
            parent_valid_assets.append(asset)

        record_ids = {
            int(asset.diet_record_id)
            for asset in parent_valid_assets
            if asset.diet_record_id is not None
        }
        draft_tokens = {
            str(asset.photo_draft_token)
            for asset in parent_valid_assets
            if asset.photo_draft_token
        }
        parent_consistent = len(record_ids) + len(draft_tokens) == 1
        if not parent_consistent:
            parent_valid_assets = []

        signed_assets: list[Any] = []
        signed_urls: list[str] = []
        for asset in parent_valid_assets:
            signed = diet_response_image_url(asset.storage_key, int(owner_id))
            if signed is None:
                continue
            signed_assets.append(asset)
            signed_urls.append(signed)

        if parent_valid_assets:
            if record_ids:
                current_record_id = next(iter(record_ids))
                data["recorded"] = True
                data["record_id"] = current_record_id
                data.pop("photo_draft_token", None)
                card["actions"] = []
            else:
                current_draft_token = next(iter(draft_tokens))
                data["recorded"] = False
                data["photo_draft_token"] = current_draft_token
                data.pop("record_id", None)

        if signed_assets:
            valid_ids = [str(asset.id) for asset in signed_assets]
            data["photo_asset_id"] = valid_ids[0]
            data["photo_asset_ids"] = valid_ids
            data["photo_url"] = signed_urls[0]
            data["photo_urls"] = signed_urls
            missing = unavailable_basis - len(signed_assets)
            if missing:
                data["photo_unavailable_count"] = missing
                data["media_stage"] = "partially_available"
            else:
                data.pop("photo_unavailable_count", None)
                data["media_stage"] = (
                    "attached" if record_ids else "pending_confirmation"
                )
        else:
            data.pop("photo_asset_id", None)
            data["photo_asset_ids"] = []
            data.pop("photo_url", None)
            data.pop("photo_urls", None)
            data["photo_unavailable_count"] = unavailable_basis
            data["media_stage"] = "unavailable"
    return delivered


def _refresh_record_quality_edits(db: Session, metas: list, owner_id: int) -> None:
    """Refresh editable meal snapshots in a delivery copy, never persisted history.

    One owner-scoped batch per 200 distinct records; no model calls or writes.
    A stale conversation/action patch must not become the next edit's baseline.
    """
    from app.models.daily_health import DietRecord
    from app.utils.number_format import format_display_number

    cards_by_id: dict[int, list[dict]] = {}
    for meta in metas:
        if not isinstance(meta, dict) or not isinstance(meta.get("cards"), list):
            continue
        for card in meta["cards"]:
            if not isinstance(card, dict) or card.get("type") != "record_quality":
                continue
            data = card.get("data")
            if not isinstance(data, dict) or data.get("domain") != "diet":
                continue
            seed = data.get("adjust_record")
            raw_id = data.get("record_id", seed.get("record_id") if isinstance(seed, dict) else None)
            if isinstance(raw_id, bool) or not str(raw_id).isdigit() or int(raw_id) <= 0:
                continue
            cards_by_id.setdefault(int(raw_id), []).append(card)

    ids = list(cards_by_id)
    fields = ("meal_type", "food_items", "calories", "protein", "carbs", "fat", "fiber")
    nutrition = (("calories", "热量", "kcal"), ("protein", "蛋白", "g"),
                 ("carbs", "碳水", "g"), ("fat", "脂肪", "g"), ("fiber", "纤维", "g"))
    for start in range(0, len(ids), 200):
        batch = ids[start:start + 200]
        records = {record.id: record for record in db.query(DietRecord).filter(
            DietRecord.user_id == owner_id, DietRecord.id.in_(batch),
        ).all()}
        for record_id in batch:
            record = records.get(record_id)
            for card in cards_by_id[record_id]:
                data = card["data"]
                if record is None:
                    card["data"] = {"domain": "diet", "title": "记录不可用",
                                    "summary": "该记录已删除或当前账号无法访问，请到饮食页核对。"}
                    card["actions"] = []
                    continue
                seed = {field: getattr(record, field) for field in fields}
                seed.update(record_id=record.id, updated_at=(
                    record.updated_at.isoformat() if record.updated_at is not None else None
                ))
                old_seed = data.get("adjust_record")
                changed = not isinstance(old_seed, dict) or any(
                    old_seed.get(field) != seed[field] for field in fields
                )
                data.update(seed)
                data["adjust_record"] = seed
                meal = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "加餐"}.get(record.meal_type, "饮食")
                data["title"] = f"{meal}已记录"
                data["summary"] = record.food_items or "已保存的饮食记录"
                data["metrics"] = [
                    {"label": label, "value": f"{format_display_number(getattr(record, field))}{unit}"}
                    for field, label, unit in nutrition if getattr(record, field) is not None
                ]
                if changed:
                    # Old totals/advice are not recomputed by this read-only projection.
                    for key in ("progress", "goal_progress", "primary_judgement", "personal_cautions",
                                "next_action", "next_meal_detail", "expanded_sections"):
                        data.pop(key, None)
                actions = card.get("actions")
                if not isinstance(actions, list):
                    continue
                refreshed = []
                for action in actions:
                    payload = action.get("payload") if isinstance(action, dict) else None
                    if isinstance(payload, dict) and action.get("action") == "ui.inline.expand":
                        if changed and payload.get("target") in ("next_meal", "goal_progress"):
                            continue
                        if payload.get("target") == "adjust_record":
                            payload["patch"] = {"expanded_sections": ["adjust_record"], "adjust_record": deepcopy(seed)}
                    refreshed.append(action)
                card["actions"] = refreshed


def _capture_origin_message_id(value: Any) -> int | None:
    capture_session_id = str(value or "").strip()
    prefix = "meal-photo:"
    if not capture_session_id.startswith(prefix):
        return None
    raw_id = capture_session_id[len(prefix):]
    if not raw_id.isdigit():
        return None
    return int(raw_id)
