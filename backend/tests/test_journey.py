"""Journey ownership, privacy and version contracts (same suite on PostgreSQL)."""
import json
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from tests.conftest import create_authenticated_user


@pytest.fixture
def journey_data(db):
    from app.models.daily_health import DietRecord
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.episode import HealthEpisode
    user, token = create_authenticated_user(db)
    other, _ = create_authenticated_user(db)
    diet = DietRecord(user_id=user.id, record_date=date(2026, 9, 22), meal_type="晚餐", food_name="私有健康原文")
    foreign = DietRecord(user_id=other.id, record_date=date(2026, 9, 22), meal_type="晚餐")
    conv = AgentConversation(user_id=user.id)
    db.add_all([diet, foreign, conv]); db.flush()
    msg = AgentMessage(conversation_id=conv.id, role="user", content="私有聊天原文", created_at=datetime(2026, 9, 22, tzinfo=timezone.utc), image_url=f"/api/v1/upload/files/chat/{user.id}/20260922_120000_{'a'*32}.jpeg")
    event = HealthEpisode(user_id=user.id, episode_type="life_event", occurred_at=datetime(2026, 9, 22, tzinfo=timezone.utc), headline="私有生活原文")
    db.add_all([msg, event]); db.commit()
    return user, {"Authorization": f"Bearer {token}"}, diet, foreign, msg, event


def body(**changes):
    return dict(city="成都", local_date="2026-09-22", timezone="Asia/Shanghai", location_source="manual", expected_version=0, confirmed=True, **changes)


def save(client, data, **changes):
    user, headers, diet, *_ = data
    payload = body(); payload.update(changes)
    return client.put(f"/api/v1/journey/places/diet/{diet.id}", headers=headers, json=payload)


def test_journey_create_update_delete_owner_version(client, db, journey_data):
    _, headers, diet, foreign, *_ = journey_data
    first = save(client, journey_data)
    assert first.status_code == 200, first.text
    place = first.json(); assert place["version"] == 1
    assert save(client, journey_data).status_code == 409
    changed = save(client, journey_data, expected_version=1, city="北京")
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert client.put(f"/api/v1/journey/places/diet/{foreign.id}", headers=headers, json=body()).status_code == 404
    assert client.delete(f"/api/v1/journey/places/{place['id']}?expected_version=1", headers=headers).status_code == 409
    assert client.delete(f"/api/v1/journey/places/{place['id']}?expected_version=2", headers=headers).status_code == 204
    assert db.get(type(diet), diet.id) is not None


@pytest.mark.parametrize("changes", [
    {"confirmed":False}, {"confirmed":1}, {"city":""}, {"city":"<script>bad</script>"}, {"city":"成都\n北京"},
    {"city":"x"*81}, {"timezone":"Not/AZone"}, {"latitude":30}, {"expected_version":True},
    {"location_source":"device", "local_date":"2001-01-01"},
])
def test_journey_rejects_invalid_write(client, journey_data, changes):
    assert save(client, journey_data, **changes).status_code == 422


def test_journey_month_and_export_whitelist(client, db, journey_data):
    _, headers, *_ = journey_data
    created = save(client, journey_data); assert created.status_code == 200
    place = created.json()
    month = client.get("/api/v1/journey/month?month=2026-09", headers=headers)
    assert month.status_code == 200 and month.json()["total"] == 1
    request = {"items":[{"place_id":place["id"], "version":1, "image_keys":[]}]}
    exported = client.post("/api/v1/journey/export-preview", headers=headers, json=request)
    assert exported.status_code == 200, exported.text
    assert set(exported.json()) == {"month", "items"}
    assert set(exported.json()["items"][0]) == {"city","local_date","kind","images"}
    assert "私有" not in exported.text
    from app.models.agent_audit_log import AgentAuditLog
    audit = db.query(AgentAuditLog).filter_by(action="journey_export_preview").one()
    assert "成都" not in json.dumps(audit.result_detail, ensure_ascii=False)
    save(client, journey_data, expected_version=1, city="北京")
    assert client.post("/api/v1/journey/export-preview", headers=headers, json=request).status_code == 409


def test_journey_city_encrypted_at_rest(client, db, journey_data):
    assert save(client, journey_data).status_code == 200
    raw = db.execute(text("SELECT city FROM journey_places")).scalar_one()
    assert "成都" not in raw and raw.startswith("gAAAA")


def test_journey_auth_required(client):
    assert client.get("/api/v1/journey/month?month=2026-09").status_code in (401,403)


@pytest.mark.parametrize("kind,index", [("diet",2),("chat_photo",4),("life_event",5)])
def test_sources_are_owner_scoped_and_have_contract(client, db, journey_data, kind, index):
    _, headers, *_ = journey_data
    response = client.get(f"/api/v1/journey/sources?kind={kind}&month=2026-09&timezone=Asia/Shanghai", headers=headers)
    assert response.status_code == 200, response.text
    content = response.json()
    assert set(content) == {"items","total","offset","limit"}
    assert content["total"] == 1
    item = content["items"][0]
    assert item["source_id"] == journey_data[index].id
    assert item["place"] is None
    assert item["date_basis"] == ("message" if kind == "chat_photo" else "record")
    assert item["image_status"] == ("ready" if kind == "chat_photo" else "none")


@pytest.mark.parametrize("invalid", [
    "https://evil.test/api/v1/upload/files/chat/OWNER/20260922_120000_aaaaaaaa.jpeg",
    "/api/v1/upload/files/chat/999999/20260922_120000_aaaaaaaa.jpeg",
    "/api/v1/upload/files/chat/20260922_120000_aaaaaaaa.jpeg",
    "/api/v1/upload/files/chat/OWNER/20260922_120000_aaaaaaaa.jpeg?signature=x",
    "/api/v1/upload/files/chat/OWNER/20260922_120000_aaaaaaaa.jpeg#fragment",
    "/api/v1/upload/files/chat/OWNER/../20260922_120000_aaaaaaaa.jpeg",
    "/api/v1/upload/files/chat/OWNER/%2e%2e.jpeg",
    "/api/v1/upload/files/chat/OWNER/latest.jpeg",
    "/api/v1/upload/files/medical/OWNER/20260922_120000_aaaaaaaa.jpeg",
    '["bad",null]', '[broken', '{"url":"bad"}',
])
def test_invalid_chat_images_are_unavailable_not_partial(client, db, journey_data, invalid):
    user, headers, _, _, msg, _ = journey_data
    valid = msg.image_url
    msg.image_url = invalid.replace("OWNER", str(user.id))
    if not invalid.startswith(("[", "{")):
        msg.image_url = json.dumps([valid, msg.image_url])
    db.commit()
    sources = client.get("/api/v1/journey/sources?kind=chat_photo&month=2026-09", headers=headers)
    assert sources.status_code == 200
    item = sources.json()["items"][0]
    assert item["image_status"] == "unavailable" and item["images"] == []
    assert client.put(f"/api/v1/journey/places/chat_photo/{msg.id}", headers=headers, json=body()).status_code == 409


def test_photo_keys_bound_to_source_and_export_rechecks_removed_image(client, db, journey_data):
    user, headers, _, _, msg, _ = journey_data
    response = client.put(f"/api/v1/journey/places/chat_photo/{msg.id}", headers=headers, json=body())
    assert response.status_code == 200
    place = response.json(); image = place["images"][0]
    assert set(image) == {"key", "url"} and image["url"] == msg.image_url
    assert "?" not in image["url"] and "#" not in image["url"]
    selection = {"items":[{"place_id": place["id"], "version":1, "image_keys":[image["key"]]}]}
    success = client.post("/api/v1/journey/export-preview", headers=headers, json=selection)
    assert success.status_code == 200 and success.json()["items"][0]["images"][0]["key"] == image["key"]
    msg.image_url = f"/api/v1/upload/files/chat/{user.id}/20260922_120001_{'b'*32}.jpeg"
    db.commit()
    assert client.post("/api/v1/journey/export-preview", headers=headers, json=selection).status_code == 409


def test_assistant_and_nonlife_sources_rejected(client, db, journey_data):
    _, headers, _, _, msg, event = journey_data
    msg.role = "assistant"; event.episode_type = "symptom"; db.commit()
    for kind, source in (("chat_photo", msg), ("life_event", event)):
        assert client.put(f"/api/v1/journey/places/{kind}/{source.id}", headers=headers, json=body()).status_code == 404


def test_export_and_place_foreign_owner_404(client, db, journey_data):
    first = save(client, journey_data).json()
    _, token = create_authenticated_user(db)
    headers = {"Authorization":f"Bearer {token}"}
    assert client.get("/api/v1/journey/month?month=2026-09", headers=headers).json()["total"] == 0
    assert client.delete(f"/api/v1/journey/places/{first['id']}?expected_version=1", headers=headers).status_code == 404
    assert client.post("/api/v1/journey/export-preview", headers=headers, json={"items":[{"place_id":first["id"],"version":1,"image_keys":[]}]}).status_code == 404


def test_export_rejects_mixed_month_duplicate_unknown_fields(client, db, journey_data):
    _, headers, _, _, msg, _ = journey_data
    p1 = save(client, journey_data).json()
    payload = body(); payload["local_date"] = "2026-08-30"
    p2 = client.put(f"/api/v1/journey/places/chat_photo/{msg.id}", headers=headers, json=payload).json()
    items = [{"place_id": p["id"], "version":1, "image_keys":[]} for p in (p1,p2)]
    for request in ({"items":items},{"items":[items[0],items[0]]},{"items":[dict(items[0], title="private")]},{"items":[]}):
        assert client.post("/api/v1/journey/export-preview", headers=headers, json=request).status_code == 422


def test_commit_failure_rolls_back_without_sensitive_error(client, db, journey_data, monkeypatch, caplog):
    def failed_commit():
        raise RuntimeError("secret city 成都 and raw payload")
    monkeypatch.setattr(db, "commit", failed_commit)
    response = save(client, journey_data)
    assert response.status_code == 503
    assert "secret city" not in response.text + caplog.text and "成都" not in caplog.text
    from app.models.journey_place import JourneyPlace
    assert db.query(JourneyPlace).count() == 0


def test_encryption_failure_never_falls_back_to_plaintext(client, db, journey_data, monkeypatch, caplog):
    from app.models import _encrypted
    class BrokenCipher:
        def encrypt(self, raw):
            raise RuntimeError("secret plaintext " + raw.decode())
    monkeypatch.setattr(_encrypted, "_fernet", BrokenCipher())
    response = save(client, journey_data)
    assert response.status_code == 503
    assert "成都" not in caplog.text + response.text
    assert db.execute(text("SELECT COUNT(*) FROM journey_places")).scalar_one() == 0


def test_audit_failure_blocks_export(client, db, journey_data, monkeypatch, caplog):
    _, headers, *_ = journey_data
    p = save(client, journey_data).json()
    original_add = db.add
    from app.models.agent_audit_log import AgentAuditLog
    def fail_audit(obj, *args, **kwargs):
        if isinstance(obj, AgentAuditLog):
            raise RuntimeError("private audit payload")
        return original_add(obj, *args, **kwargs)
    monkeypatch.setattr(db, "add", fail_audit)
    response = client.post("/api/v1/journey/export-preview", headers=headers, json={"items":[{"place_id":p["id"],"version":1,"image_keys":[]}]})
    assert response.status_code == 503 and "private audit payload" not in response.text + caplog.text


def test_month_pagination_total_and_confirmation_date_not_source_date(client, db, journey_data):
    _, headers, _, _, msg, _ = journey_data
    save(client, journey_data)
    payload = body(); payload["local_date"] = "2026-08-31"
    assert client.put(f"/api/v1/journey/places/chat_photo/{msg.id}", headers=headers, json=payload).status_code == 200
    aug = client.get("/api/v1/journey/month?month=2026-08&limit=1", headers=headers).json()
    sep = client.get("/api/v1/journey/month?month=2026-09&offset=1&limit=1", headers=headers).json()
    assert aug["total"] == 1 and aug["items"][0]["local_date"] == "2026-08-31"
    assert sep["total"] == 1 and sep["items"] == []


def test_source_timezone_natural_month_boundaries(client, db, journey_data):
    _, headers, _, _, msg, event = journey_data
    # chat persisted naive means UTC, while old SQLite life_event naive is CST.
    msg.created_at = datetime(2026, 8, 31, 17)
    event.occurred_at = datetime(2026, 8, 31, 17, tzinfo=timezone.utc) if db.get_bind().dialect.name == "postgresql" else datetime(2026, 9, 1, 1)
    db.commit(); db.expire_all()
    for kind in ("chat_photo","life_event"):
        china = client.get(f"/api/v1/journey/sources?kind={kind}&month=2026-09&timezone=Asia/Shanghai", headers=headers).json()
        utc = client.get(f"/api/v1/journey/sources?kind={kind}&month=2026-08&timezone=UTC", headers=headers).json()
        assert china["total"] == 1 and china["items"][0]["suggested_date"] == "2026-09-01"
        assert utc["total"] == 1 and utc["items"][0]["suggested_date"] == "2026-08-31"


def test_plaintext_corruption_read_fails_without_exposing_city(client, db, journey_data, caplog):
    _, headers, *_ = journey_data
    assert save(client, journey_data).status_code == 200
    db.execute(text("UPDATE journey_places SET city=:city"), {"city":"plaintext-private-city"}); db.commit(); db.expire_all()
    response = client.get("/api/v1/journey/month?month=2026-09", headers=headers)
    assert response.status_code == 503
    assert "plaintext-private-city" not in response.text + caplog.text


def test_diet_bad_photo_is_explicit_but_text_only_place_allowed(client, db, journey_data):
    _, headers, diet, *_ = journey_data
    diet.image_url = "https://evil.test/image.jpeg"; db.commit()
    response = save(client, journey_data)
    assert response.status_code == 200
    assert response.json()["image_status"] == "unavailable" and response.json()["images"] == []


def test_diet_ledger_owner_mismatch_unavailable(client, db, journey_data):
    from app.models.daily_health import DietPhotoAsset
    user, headers, diet, foreign, *_ = journey_data
    db.add(DietPhotoAsset(id="journey-test-asset", user_id=foreign.user_id, diet_record_id=diet.id,
                         storage_key=f"/api/v1/upload/files/diet/{user.id}/20260922_120000_aaaaaaaa.jpeg",
                         content_sha256="b"*64, media_type="image/jpeg", origin="manual", ordinal=0,
                         classification="food", intent_decision="auto_record", lifecycle="attached"))
    db.commit()
    response = save(client, journey_data)
    assert response.status_code == 200 and response.json()["image_status"] == "unavailable"


def test_stable_photo_key_not_signature_or_source_reusable(db, journey_data):
    from app.services.journey_images import source_images
    user, _, _, _, msg, _ = journey_data
    first, _ = source_images("chat_photo", msg, user.id)
    second, _ = source_images("chat_photo", msg, user.id)
    assert first[0]["key"] == second[0]["key"]
    # Same photo in a different source has a different confirmation key.
    from types import SimpleNamespace
    other = SimpleNamespace(id=msg.id+1, image_url=msg.image_url)
    third, _ = source_images("chat_photo", other, user.id)
    assert third[0]["key"] != first[0]["key"]


@pytest.mark.parametrize("query", ["month=2026-99", "month=bad", "month=2026-09&limit=0", "month=2026-09&offset=-1", "month=2026-09&limit=101"])
def test_invalid_month_and_page_boundary(client, journey_data, query):
    assert client.get(f"/api/v1/journey/month?{query}", headers=journey_data[1]).status_code == 422


def test_deleted_diet_asset_must_not_be_resigned_from_stale_cover(client, db, journey_data):
    from app.models.daily_health import DietPhotoAsset
    user, headers, diet, *_ = journey_data
    diet.image_url = f"/api/v1/upload/files/diet/{user.id}/20260922_120000_aaaaaaaa.jpeg"
    asset = DietPhotoAsset(id="journey-deleted-asset", user_id=user.id, diet_record_id=diet.id,
                          storage_key=diet.image_url, content_sha256="b"*64, media_type="image/jpeg",
                          origin="manual", ordinal=0, classification="food", intent_decision="auto_record", lifecycle="attached")
    db.add(asset); db.commit()
    place = save(client, journey_data).json()
    assert place["image_status"] == "ready"
    selection = {"items":[{"place_id":place["id"],"version":1,"image_keys":[place["images"][0]["key"]]}]}
    asset.lifecycle = "deleted"; db.commit(); db.expire_all()
    response = client.post("/api/v1/journey/export-preview", headers=headers, json=selection)
    assert response.status_code == 409
    current = client.get("/api/v1/journey/month?month=2026-09", headers=headers).json()["items"][0]
    assert current["images"] == [] and current["image_status"] == "unavailable"


@pytest.mark.parametrize("kind,index,category", [("chat_photo",4,"chat"),("diet",2,"diet")])
def test_journey_image_endpoint_needs_authenticated_owner(client, db, journey_data, tmp_path, monkeypatch, kind, index, category):
    from app.api import upload
    user, headers, *_ = journey_data
    source = journey_data[index]
    filename = "20260922_120000_aaaaaaaa.jpeg"
    canonical = f"/api/v1/upload/files/{category}/{user.id}/{filename}"
    source.image_url = canonical; db.commit()
    directory = tmp_path / category / str(user.id); directory.mkdir(parents=True)
    (directory / filename).write_bytes(b"synthetic-image-content")
    monkeypatch.setattr(upload, "UPLOAD_DIR", str(tmp_path))
    response = client.put(f"/api/v1/journey/places/{kind}/{source.id}", headers=headers, json=body())
    assert response.status_code == 200
    url = response.json()["images"][0]["url"]
    assert url == canonical
    owner_read = client.get(url, headers=headers)
    assert owner_read.status_code == 200 and owner_read.content == b"synthetic-image-content"
    assert client.get(url).status_code == 401
    _, token = create_authenticated_user(db)
    assert client.get(url, headers={"Authorization":f"Bearer {token}"}).status_code == 403
