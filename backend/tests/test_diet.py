"""饮食记录API测试"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from app.models.user import User
from app.models.daily_health import DietPhotoAsset, DietPhotoDraft, DietRecord
from app.models.food_nutrition import FoodItem, FoodNutrient
from app.services.internal_diet_correction import (
    INTERNAL_DIET_PORTION_SIGNATURE_HEADER,
    build_internal_diet_portion_signature,
)


VALID_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z/QAAAABJRU5ErkJggg=="


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password="hashed_password",
        name="测试用户",
        is_active=True,
        is_approved=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(client, test_user):
    """获取认证 headers"""
    # 创建一个简单的认证方式
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_diet_data():
    """示例饮食数据"""
    return {
        "record_date": str(date.today()),
        "meal_type": "breakfast",
        "food_items": "鸡蛋,牛奶,面包",
        "calories": 450,
        "protein": 20.5,
        "carbs": 45.0,
        "fat": 15.0,
        "notes": "健康早餐"
    }


class TestDietAPI:
    """饮食记录API测试类"""

    def test_create_diet_record(self, client, auth_headers, sample_diet_data):
        """测试创建饮食记录"""
        response = client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["meal_type"] == "breakfast"
        assert data["food_items"] == "鸡蛋,牛奶,面包"
        assert data["calories"] == 450
        assert data["protein"] == 20.5
        assert "id" in data

    def test_create_diet_record_minimal(self, client, auth_headers):
        """测试创建最小饮食记录（只有必填字段）"""
        minimal_data = {
            "record_date": str(date.today()),
            "meal_type": "lunch",
            "food_items": "米饭,青菜"
        }
        response = client.post(
            "/api/v1/diet/records",
            json=minimal_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["meal_type"] == "lunch"
        assert data["food_items"] == "米饭,青菜"
        assert data["calories"] is None

    def test_direct_photo_record_creates_attached_photo_asset(
        self, client, db, auth_headers, sample_diet_data, tmp_path, monkeypatch
    ):
        from app.api import upload as upload_api

        monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(tmp_path / "uploads"))
        response = client.post(
            "/api/v1/diet/records",
            json={
                **sample_diet_data,
                "image_base64": VALID_PNG_BASE64,
                "image_type": "png",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        asset = db.query(DietPhotoAsset).one()
        assert asset.diet_record_id == body["id"]
        assert asset.photo_draft_token is None
        assert asset.lifecycle == "attached"
        assert asset.storage_key.startswith("/api/v1/upload/files/diet/")
        assert body["photo_assets"][0]["id"] == asset.id
        assert body["image_urls"] == [body["photo_assets"][0]["url"]]

    def test_diet_record_returns_ordered_signed_photo_assets(
        self, client, db, auth_headers, test_user, sample_diet_data
    ):
        created = client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers,
        )
        assert created.status_code == 200
        record_id = created.json()["id"]
        canonical_cover = (
            f"/api/v1/upload/files/diet/{test_user.id}/lunch-cover.jpg"
        )
        canonical_second = (
            f"/api/v1/upload/files/diet/{test_user.id}/lunch-side.jpg"
        )
        db.add_all([
            DietPhotoAsset(
                id="diet-asset-cover",
                user_id=test_user.id,
                diet_record_id=record_id,
                storage_key=canonical_cover,
                content_sha256="a" * 64,
                media_type="image/jpeg",
                origin="chat",
                ordinal=0,
                classification="food",
                recognition_confidence=0.94,
                intent_decision="auto_record",
                recognition_snapshot={"food_count": 2},
                lifecycle="attached",
            ),
            DietPhotoAsset(
                id="diet-asset-side",
                user_id=test_user.id,
                diet_record_id=record_id,
                storage_key=canonical_second,
                content_sha256="b" * 64,
                media_type="image/jpeg",
                origin="chat",
                ordinal=1,
                classification="food",
                recognition_confidence=0.94,
                intent_decision="auto_record",
                recognition_snapshot={"food_count": 2},
                lifecycle="attached",
            ),
        ])
        db.commit()

        response = client.get("/api/v1/diet/records/me", headers=auth_headers)

        assert response.status_code == 200
        payload = next(item for item in response.json() if item["id"] == record_id)
        assert [asset["id"] for asset in payload["photo_assets"]] == [
            "diet-asset-cover",
            "diet-asset-side",
        ]
        assert [asset["ordinal"] for asset in payload["photo_assets"]] == [0, 1]
        assert payload["image_url"].startswith(canonical_cover + "?")
        assert payload["image_urls"] == [
            payload["photo_assets"][0]["url"],
            payload["photo_assets"][1]["url"],
        ]
        assert all("?expires=" in url for url in payload["image_urls"])
        assert db.query(DietPhotoAsset).filter_by(id="diet-asset-cover").one().storage_key == canonical_cover

    def test_diet_photo_asset_rejects_signed_url_as_persistent_storage_key(
        self, db, test_user
    ):
        db.add(DietPhotoAsset(
            id="diet-asset-signed-url",
            user_id=test_user.id,
            storage_key=(
                f"/api/v1/upload/files/diet/{test_user.id}/meal.jpg?expires=1&signature=x"
            ),
            content_sha256="c" * 64,
            media_type="image/jpeg",
            origin="chat",
            ordinal=0,
            classification="food",
            intent_decision="confirm",
            recognition_snapshot={},
            lifecycle="pending",
        ))

        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_confirming_photo_draft_attaches_pending_asset_to_created_record(
        self, client, db, auth_headers, test_user, sample_diet_data, monkeypatch
    ):
        from contextlib import contextmanager

        from app.services.contextual_meal_photo_service import (
            ContextualMealPhotoService,
        )

        token = "contextual-photo-draft-token-0001"
        source_message_id = 99101
        canonical_path = f"/api/v1/upload/files/diet/{test_user.id}/pending-lunch.jpg"
        draft = DietPhotoDraft(
            token=token,
            user_id=test_user.id,
            source_message_id=source_message_id,
            image_url=canonical_path,
            image_type="jpeg",
            recognition_result={"food_items": "鸡胸肉 120g"},
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        asset = DietPhotoAsset(
            id="diet-asset-pending-confirmation",
            user_id=test_user.id,
            photo_draft_token=token,
            storage_key=canonical_path,
            content_sha256="d" * 64,
            media_type="image/jpeg",
            origin="chat",
            origin_message_id=source_message_id,
            ordinal=0,
            classification="food",
            recognition_confidence=0.91,
            intent_decision="confirm",
            recognition_snapshot={"food_count": 1},
            lifecycle="pending",
        )
        db.add_all([draft, asset])
        db.commit()
        capture_locks = []

        @contextmanager
        def capture_session_lock(_service, user_id, message_id):
            capture_locks.append((user_id, message_id))
            yield

        monkeypatch.setattr(
            ContextualMealPhotoService,
            "_capture_session_lock",
            capture_session_lock,
        )

        response = client.post(
            "/api/v1/diet/records",
            json={**sample_diet_data, "photo_draft_token": token},
            headers={
                **auth_headers,
                "Idempotency-Key": "op_runtime-photo-confirmation-0001",
            },
        )

        assert response.status_code == 200
        assert capture_locks == [(test_user.id, source_message_id)]
        record_id = response.json()["id"]
        db.refresh(asset)
        assert asset.diet_record_id == record_id
        assert asset.photo_draft_token is None
        assert asset.lifecycle == "attached"
        assert response.json()["image_urls"] == [response.json()["photo_assets"][0]["url"]]
        stored = db.query(DietRecord).filter_by(id=record_id).one()
        assert stored.client_action_id == (
            "op_runtime-photo-confirmation-0001|"
            f"diet-photo:{token}"
        )

    def test_create_diet_record_reuses_user_scoped_idempotency_key(
        self, client, db, auth_headers, sample_diet_data
    ):
        headers = {**auth_headers, "Idempotency-Key": "chat-card-lunch-77"}

        first = client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=headers,
        )
        second = client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=headers,
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert db.query(DietRecord).count() == 1
        assert db.query(DietRecord).one().client_action_id == "chat-card-lunch-77"

    def test_create_diet_record_invalid_meal_type(self, client, auth_headers):
        """测试创建饮食记录（无效的餐类型）"""
        invalid_data = {
            "record_date": str(date.today()),
            "meal_type": "invalid_type",
            "food_items": "测试食物"
        }
        response = client.post(
            "/api/v1/diet/records",
            json=invalid_data,
            headers=auth_headers
        )
        assert response.status_code == 422  # 验证错误

    def test_create_diet_record_missing_food_items(self, client, auth_headers):
        """测试创建饮食记录（缺少食物）"""
        invalid_data = {
            "record_date": str(date.today()),
            "meal_type": "breakfast"
            # 缺少 food_items
        }
        response = client.post(
            "/api/v1/diet/records",
            json=invalid_data,
            headers=auth_headers
        )
        assert response.status_code == 422

    def test_create_diet_record_unauthorized(self, client, sample_diet_data):
        """测试未授权创建饮食记录"""
        response = client.post(
            "/api/v1/diet/records",
            json=sample_diet_data
        )
        assert response.status_code == 401

    def test_create_diet_record_ignores_client_controlled_image_url(
        self, client, db, auth_headers, sample_diet_data
    ):
        response = client.post(
            "/api/v1/diet/records",
            json={
                **sample_diet_data,
                "image_url": "/api/v1/upload/files/diet/victim.jpg",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["image_url"] is None
        assert db.query(DietRecord).one().image_url is None

    @pytest.mark.parametrize("food_items", [
        "我刚才不小心删除了",
        "删除这一餐",
        "替普瑞酮胶囊（施维舒）",
        "鱼油",
        "和午餐食品营养卡",
        "保存并确认",
        "沃克",
        "伏诺拉生",
        "晨跑 30 分钟",
        "体重 73.1kg 腰围 84cm",
        "昨晚睡了 6 小时",
        "血压 130/85 血糖 6.2",
    ])
    def test_create_diet_record_rejects_non_food_items(self, client, auth_headers, food_items):
        """REST API 防御纵深: 管理意图/药物/补剂不能直接落成 DietRecord。"""
        response = client.post(
            "/api/v1/diet/records",
            json={
                "record_date": str(date.today()),
                "meal_type": "dinner",
                "food_items": food_items,
            },
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "不能作为饮食记录" in response.json()["detail"]

    def test_image_persistence_failure_fails_the_write_without_creating_a_record(
        self, client, db, auth_headers, sample_diet_data, tmp_path, monkeypatch
    ):
        from app.api import upload as upload_api

        blocked_root = tmp_path / "not-a-directory"
        blocked_root.write_text("occupied")
        monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(blocked_root))

        response = client.post(
            "/api/v1/diet/records",
            json={
                **sample_diet_data,
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
                "image_type": "png",
            },
            headers=auth_headers,
        )

        assert response.status_code == 500
        assert db.query(DietRecord).count() == 0

    def test_idempotency_conflict_removes_the_losing_private_image(
        self, db, test_user, sample_diet_data, tmp_path, monkeypatch
    ):
        from sqlalchemy.exc import IntegrityError

        from app.api import upload as upload_api
        from app.api.diet import create_diet_record
        from app.schemas.diet import DietRecordCreate

        key = "diet-card-conflict-1"
        existing = DietRecord(
            user_id=test_user.id,
            record_date=date.today(),
            meal_type="lunch",
            food_name="既有午餐",
            food_items="既有午餐",
            client_action_id=key,
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)

        upload_root = tmp_path / "uploads"
        monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(upload_root))
        real_query = db.query
        diet_query_count = 0

        class QueryResult:
            def __init__(self, value):
                self.value = value

            def filter(self, *args, **kwargs):
                return self

            def first(self):
                return self.value

        def query(model, *args, **kwargs):
            nonlocal diet_query_count
            if model is DietRecord:
                diet_query_count += 1
                return QueryResult(None if diet_query_count == 1 else existing)
            return real_query(model, *args, **kwargs)

        def conflicting_commit():
            raise IntegrityError("insert", {}, Exception("duplicate"))

        monkeypatch.setattr(db, "query", query)
        monkeypatch.setattr(db, "commit", conflicting_commit)
        result = create_diet_record(
            DietRecordCreate(
                **sample_diet_data,
                image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
                image_type="png",
            ),
            current_user=test_user,
            db=db,
            idempotency_key=key,
        )

        assert result.id == existing.id
        assert list((upload_root / "diet" / str(test_user.id)).glob("*")) == []

    def test_delete_diet_record_removes_its_private_image(
        self, client, auth_headers, test_user, sample_diet_data, tmp_path, monkeypatch
    ):
        from app.api import upload as upload_api

        upload_root = tmp_path / "uploads"
        monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(upload_root))
        created = client.post(
            "/api/v1/diet/records",
            json={
                **sample_diet_data,
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
                "image_type": "png",
            },
            headers=auth_headers,
        )
        assert created.status_code == 200
        files = list((upload_root / "diet" / str(test_user.id)).glob("*"))
        assert len(files) == 1

        deleted = client.delete(
            f"/api/v1/diet/records/{created.json()['id']}",
            headers=auth_headers,
        )

        assert deleted.status_code == 200
        assert not files[0].exists()

    def test_delete_diet_record_removes_all_attached_photo_assets(
        self, client, db, auth_headers, test_user, sample_diet_data, tmp_path, monkeypatch
    ):
        from app.api import upload as upload_api

        upload_root = tmp_path / "uploads"
        owner_root = upload_root / "diet" / str(test_user.id)
        owner_root.mkdir(parents=True)
        monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(upload_root))
        created = client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers,
        )
        assert created.status_code == 200
        record_id = created.json()["id"]

        cover = owner_root / "cover.jpg"
        side = owner_root / "side.jpg"
        cover.write_bytes(b"cover")
        side.write_bytes(b"side")
        db.add_all([
            DietPhotoAsset(
                id="delete-cover", user_id=test_user.id, diet_record_id=record_id,
                storage_key=f"/api/v1/upload/files/diet/{test_user.id}/cover.jpg",
                content_sha256="c" * 64, media_type="image/jpeg", origin="chat",
                ordinal=0, classification="food", recognition_confidence=0.9,
                intent_decision="auto_record", lifecycle="attached",
            ),
            DietPhotoAsset(
                id="delete-side", user_id=test_user.id, diet_record_id=record_id,
                storage_key=f"/api/v1/upload/files/diet/{test_user.id}/side.jpg",
                content_sha256="s" * 64, media_type="image/jpeg", origin="chat",
                ordinal=1, classification="food", recognition_confidence=0.9,
                intent_decision="auto_record", lifecycle="attached",
            ),
        ])
        db.commit()

        deleted = client.delete(f"/api/v1/diet/records/{record_id}", headers=auth_headers)

        assert deleted.status_code == 200
        assert not cover.exists()
        assert not side.exists()
        assert db.query(DietPhotoAsset).filter(DietPhotoAsset.id.in_(["delete-cover", "delete-side"])).count() == 0

    def test_delete_diet_record_retries_a_failed_private_image_cleanup(
        self, client, db, auth_headers, test_user, sample_diet_data, tmp_path, monkeypatch
    ):
        from app.api import diet as diet_api
        from app.api import upload as upload_api

        upload_root = tmp_path / "uploads"
        monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(upload_root))
        created = client.post(
            "/api/v1/diet/records",
            json={
                **sample_diet_data,
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
                "image_type": "png",
            },
            headers=auth_headers,
        )
        assert created.status_code == 200
        real_remove = diet_api._remove_diet_image_file

        def fail_tombstone_once(path):
            if path and ".deleting-" in str(path):
                raise OSError("disk busy")
            return real_remove(path)

        monkeypatch.setattr(diet_api, "_remove_diet_image_file", fail_tombstone_once)
        deleted = client.delete(
            f"/api/v1/diet/records/{created.json()['id']}",
            headers=auth_headers,
        )

        assert deleted.status_code == 200
        owner_root = upload_root / "diet" / str(test_user.id)
        assert len(list(owner_root.glob("*.deleting-*"))) == 1
        assert db.query(DietRecord).filter(DietRecord.id == created.json()["id"]).first() is None

        monkeypatch.setattr(diet_api, "_remove_diet_image_file", real_remove)
        assert diet_api.reconcile_staged_diet_image_deletions(db) == 1
        assert list(owner_root.glob("*")) == []

    def test_delete_diet_record_keeps_record_when_image_lock_is_busy(
        self, client, db, auth_headers, test_user, sample_diet_data, tmp_path, monkeypatch
    ):
        from app.api import diet as diet_api
        from app.api import upload as upload_api

        upload_root = tmp_path / "uploads"
        monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(upload_root))
        created = client.post(
            "/api/v1/diet/records",
            json={
                **sample_diet_data,
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
                "image_type": "png",
            },
            headers=auth_headers,
        )
        assert created.status_code == 200
        image_path = next((upload_root / "diet" / str(test_user.id)).glob("*"))
        monkeypatch.setattr(diet_api, "_stage_diet_image_delete", lambda *_args: None)

        deleted = client.delete(
            f"/api/v1/diet/records/{created.json()['id']}",
            headers=auth_headers,
        )

        assert deleted.status_code == 409
        assert image_path.exists()
        assert db.query(DietRecord).filter(DietRecord.id == created.json()["id"]).one()

    def test_diet_image_tombstone_is_restored_when_record_still_references_it(
        self, db, test_user, tmp_path, monkeypatch
    ):
        from app.api import diet as diet_api
        from app.api import upload as upload_api

        upload_root = tmp_path / "uploads"
        owner_root = upload_root / "diet" / str(test_user.id)
        owner_root.mkdir(parents=True)
        original = owner_root / "referenced.png"
        original.write_bytes(b"private-image")
        monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(upload_root))
        record = DietRecord(
            user_id=test_user.id,
            record_date=date.today(),
            meal_type="lunch",
            food_items="仍在引用的午餐",
            image_url=f"/api/v1/upload/files/diet/{test_user.id}/referenced.png",
        )
        db.add(record)
        db.commit()

        staged = diet_api._stage_diet_image_delete(record.image_url, test_user.id)
        assert staged is not None
        diet_api._release_staged_diet_image_lock(staged)
        assert not original.exists()

        assert diet_api.reconcile_staged_diet_image_deletions(db) == 1
        assert original.read_bytes() == b"private-image"

    def test_delete_diet_record_never_deletes_a_legacy_global_image(
        self, client, db, auth_headers, test_user, tmp_path, monkeypatch
    ):
        from app.api import upload as upload_api

        upload_root = tmp_path / "uploads"
        legacy_dir = upload_root / "diet"
        legacy_dir.mkdir(parents=True)
        legacy_file = legacy_dir / "shared-legacy.jpg"
        legacy_file.write_bytes(b"legacy-private-image")
        monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(upload_root))
        record = DietRecord(
            user_id=test_user.id,
            record_date=date.today(),
            meal_type="lunch",
            food_name="旧午餐",
            food_items="旧午餐",
            image_url="/api/v1/upload/files/diet/shared-legacy.jpg",
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        deleted = client.delete(
            f"/api/v1/diet/records/{record.id}",
            headers=auth_headers,
        )

        assert deleted.status_code == 200
        assert legacy_file.exists()

    def test_editing_food_clears_stale_nutrition_and_ai_provenance(
        self, client, db, auth_headers, test_user
    ):
        record = DietRecord(
            user_id=test_user.id,
            record_date=date.today(),
            meal_type="lunch",
            food_items="鸡胸肉 200g",
            food_id="cfc:chicken_breast",
            source="china_food_composition",
            calories=330,
            protein=62,
            carbs=0,
            fat=7.2,
            fiber=0,
            ai_recognized=True,
            ai_confidence=0.92,
            ai_raw_result='{"foods":[{"name":"鸡胸肉"}]}',
            health_tips="旧模型建议",
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        updated = client.put(
            f"/api/v1/diet/records/{record.id}",
            json={
                "food_items": "三文鱼 180g",
                "calories": 330,
                "protein": 62,
                "carbs": 0,
                "fat": 7.2,
            },
            headers=auth_headers,
        )

        assert updated.status_code == 200
        assert updated.json()["source"] == "user_corrected"
        assert updated.json()["food_id"] is None
        assert updated.json()["calories"] is None
        assert updated.json()["protein"] is None
        db.refresh(record)
        assert record.ai_recognized is False
        assert record.ai_confidence is None
        assert record.ai_raw_result is None
        assert record.health_tips is None

    def test_photo_draft_status_fails_closed_after_expiry(
        self, client, db, auth_headers, test_user
    ):
        draft = DietPhotoDraft(
            token="expired-status-photo-draft-123456",
            user_id=test_user.id,
            image_url=None,
            image_type="jpeg",
            recognition_result={"success": True, "foods": [{"name": "私有餐食"}]},
            status="pending",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        db.add(draft)
        db.commit()

        response = client.get(
            f"/api/v1/diet/photo-drafts/{draft.token}/status",
            headers=auth_headers,
        )

        assert response.status_code == 410
        assert db.query(DietPhotoDraft).filter_by(token=draft.token).first() is None

    def test_legacy_diet_image_fields_reject_signed_urls(self, db, test_user):
        signed_url = (
            f"/api/v1/upload/files/diet/{test_user.id}/meal.jpg?expires=1&signature=x"
        )
        db.add(DietRecord(
            user_id=test_user.id,
            record_date=date.today(),
            meal_type="lunch",
            food_name="签名路径测试",
            food_items="签名路径测试",
            image_url=signed_url,
        ))

        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.add(DietPhotoDraft(
            token="signed-url-photo-draft-123456",
            user_id=test_user.id,
            image_url=signed_url,
            image_type="jpeg",
            recognition_result={},
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_explicit_past_record_date_is_preserved(
        self, client, auth_headers
    ):
        """The API must never silently move a meal to a different day."""
        from datetime import datetime, timedelta, timezone

        server_today = datetime.now(timezone(timedelta(hours=8))).date()
        historical_date = server_today - timedelta(days=3)

        response = client.post(
            "/api/v1/diet/records",
            json={
                "record_date": str(historical_date),
                "meal_type": "lunch",
                "food_items": "wagas 沙拉",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["record_date"] == str(historical_date)

    def test_two_day_backfill_is_allowed_not_clamped(self, client, auth_headers):
        """合法补录: ±2 天以内的日期照原样保留, 不被钳制 (真实补录场景)。"""
        from datetime import datetime, timedelta, timezone

        server_today = datetime.now(timezone(timedelta(hours=8))).date()
        two_days_ago = server_today - timedelta(days=2)  # 恰好 2 天, 属允许区间

        response = client.post(
            "/api/v1/diet/records",
            json={
                "record_date": str(two_days_ago),
                "meal_type": "dinner",
                "food_items": "补录的晚餐",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["record_date"] == str(two_days_ago)

    def test_get_my_diet_records(self, client, auth_headers, sample_diet_data):
        """测试获取我的饮食记录"""
        # 先创建记录
        client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers
        )

        # 获取记录
        response = client.get(
            "/api/v1/diet/records/me",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.parametrize("path_suffix", [
        "",
        f"/date/{date.today()}",
        "/stats",
    ])
    def test_user_scoped_diet_routes_reject_cross_user_reads(
        self, client, db, auth_headers, path_suffix
    ):
        identity = (path_suffix or "list").replace("/", "-")
        other_user = User(
            username=f"other-diet-user{identity}",
            email=f"other-diet-user{identity}@example.com",
            hashed_password="hashed_password",
            name="其他用户",
            is_active=True,
            is_approved=True,
        )
        db.add(other_user)
        db.commit()
        db.refresh(other_user)

        response = client.get(
            f"/api/v1/diet/records/user/{other_user.id}{path_suffix}",
            headers=auth_headers,
        )

        assert response.status_code == 403

    def test_get_my_daily_summary(self, client, auth_headers, sample_diet_data):
        """测试获取我的每日饮食汇总"""
        # 先创建记录
        client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers
        )

        # 获取汇总
        today = str(date.today())
        response = client.get(
            f"/api/v1/diet/records/me/date/{today}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["record_date"] == today
        assert data["total_calories"] == 450
        assert data["meals_count"] == 1

    def test_get_my_diet_stats(self, client, auth_headers, sample_diet_data):
        """测试获取我的饮食统计"""
        # 先创建记录
        client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers
        )

        # 获取统计
        response = client.get(
            "/api/v1/diet/records/me/stats?days=7",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_records"] >= 1
        assert data["days_recorded"] >= 1

    def test_delete_diet_record(self, client, auth_headers, sample_diet_data):
        """测试删除饮食记录"""
        # 先创建记录
        create_response = client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers
        )
        record_id = create_response.json()["id"]

        # 删除记录
        delete_response = client.delete(
            f"/api/v1/diet/records/{record_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200

        # 验证删除成功
        today = str(date.today())
        get_response = client.get(
            f"/api/v1/diet/records/me/date/{today}",
            headers=auth_headers
        )
        assert get_response.json()["meals_count"] == 0

    def test_update_diet_record(self, client, auth_headers, sample_diet_data):
        """测试更新饮食记录"""
        # 先创建记录
        create_response = client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers
        )
        record_id = create_response.json()["id"]

        # 更新记录
        update_data = {
            "calories": 500,
            "meal_type": "dinner",
            "meal_time": "18:30:00",
            "notes": "更新后的备注",
        }
        update_response = client.put(
            f"/api/v1/diet/records/{record_id}",
            json=update_data,
            headers=auth_headers
        )
        assert update_response.status_code == 200
        assert update_response.json()["calories"] == 500
        assert update_response.json()["meal_type"] == "dinner"
        assert update_response.json()["meal_time"] == "18:30:00"
        assert update_response.json()["notes"] == "更新后的备注"

    def test_public_source_cannot_bypass_stale_nutrition_invalidation(
        self, client, auth_headers, sample_diet_data
    ):
        created = client.post(
            "/api/v1/diet/records",
            json={**sample_diet_data, "fiber": 0},
            headers=auth_headers,
        )
        assert created.status_code == 200
        original = created.json()

        updated = client.put(
            f"/api/v1/diet/records/{original['id']}",
            json={
                "food_items": f"{original['food_items']}（按实际食用1/1计）",
                "source": "agent_portion_correction",
                "calories": original["calories"],
                "protein": original["protein"],
                "carbs": original["carbs"],
                "fat": original["fat"],
                "fiber": original["fiber"],
            },
            headers=auth_headers,
        )

        assert updated.status_code == 200
        body = updated.json()
        assert body["calories"] is None
        assert body["protein"] is None
        assert body["carbs"] is None
        assert body["fat"] is None
        assert body["fiber"] is None

        trusted_created = client.post(
            "/api/v1/diet/records",
            json={
                **sample_diet_data,
                "food_items": "鸡蛋,牛奶,全麦面包",
                "fiber": 0,
            },
            headers=auth_headers,
        )
        assert trusted_created.status_code == 200
        trusted_original = trusted_created.json()
        trusted_payload = {
            "meal_type": trusted_original["meal_type"],
            "food_items": (
                f"{trusted_original['food_items']}（按实际食用1/1计）"
            ),
            "calories": trusted_original["calories"],
            "protein": trusted_original["protein"],
            "carbs": trusted_original["carbs"],
            "fat": trusted_original["fat"],
            "fiber": trusted_original["fiber"],
        }
        signature = build_internal_diet_portion_signature(
            trusted_original["user_id"],
            trusted_original["id"],
            trusted_payload,
        )

        trusted_update = client.put(
            f"/api/v1/diet/records/{trusted_original['id']}",
            json=trusted_payload,
            headers={
                **auth_headers,
                INTERNAL_DIET_PORTION_SIGNATURE_HEADER: signature,
            },
        )

        assert trusted_update.status_code == 200
        trusted_body = trusted_update.json()
        assert trusted_body["calories"] == trusted_original["calories"]
        assert trusted_body["protein"] == trusted_original["protein"]
        assert trusted_body["carbs"] == trusted_original["carbs"]
        assert trusted_body["fat"] == trusted_original["fat"]
        assert trusted_body["fiber"] == 0

    def test_update_diet_record_rejects_non_food_items(self, client, auth_headers, sample_diet_data):
        """更新饮食记录也不能把药物/删除意图写进 food_items。"""
        create_response = client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers
        )
        record_id = create_response.json()["id"]

        update_response = client.put(
            f"/api/v1/diet/records/{record_id}",
            json={"food_items": "替普瑞酮胶囊（施维舒）"},
            headers=auth_headers,
        )

        assert update_response.status_code == 400
        assert "不能作为饮食记录" in update_response.json()["detail"]

    def test_update_diet_record_ignores_client_controlled_image_url(
        self, client, db, auth_headers, sample_diet_data
    ):
        created = client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers,
        )

        updated = client.put(
            f"/api/v1/diet/records/{created.json()['id']}",
            json={"image_url": "/api/v1/upload/files/diet/victim.jpg"},
            headers=auth_headers,
        )

        assert updated.status_code == 200
        assert updated.json()["image_url"] is None
        assert db.query(DietRecord).one().image_url is None

    def test_recognize_food_calibrates_explicit_weight_from_food_table(
        self, client, db, auth_headers, monkeypatch
    ):
        from app.services.ai.food_recognition import food_recognition_service

        db.add(FoodItem(
            food_id="cfc:chicken_breast",
            canonical_name="鸡胸肉",
            aliases=["鸡肉"],
            calibration_names=["鸡胸肉"],
            locale="zh-CN",
            source="china_food_composition",
            source_ref="test-fixture",
        ))
        db.add(FoodNutrient(
            food_id="cfc:chicken_breast",
            kcal_per_100g=165.0,
            protein_g_per_100g=31.0,
            carbs_g_per_100g=0.0,
            fat_g_per_100g=3.6,
            fiber_g_per_100g=0.0,
            source="china_food_composition",
            source_ref="test-fixture",
        ))
        db.commit()

        async def recognize(*_args, **_kwargs):
            return {
                "success": True,
                "foods": [{
                    "name": "鸡胸肉",
                    "quantity": "200g",
                    "calories": 999,
                    "protein": 1,
                    "carbs": 50,
                    "fat": 40,
                    "fiber": 8,
                    "confidence": 0.91,
                }],
                "meal_description": "今日饮食营养卡",
                "total_calories": 999,
                "total_protein": 1,
                "total_carbs": 50,
                "total_fat": 40,
                "total_fiber": 8,
            }

        monkeypatch.setattr(food_recognition_service, "is_available", lambda: True)
        monkeypatch.setattr(food_recognition_service, "recognize_food_from_base64", recognize)

        response = client.post(
            "/api/v1/diet/recognize",
            json={"image_base64": "ZmFrZQ==", "image_type": "jpeg"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["meal_description"] == "鸡胸肉 200g"
        assert body["total_calories"] == 330
        assert body["total_protein"] == 62.0
        assert body["total_fiber"] == 0.0
        assert body["foods"][0]["food_id"] == "cfc:chicken_breast"
        assert body["foods"][0]["source"] == "china_food_composition"
        assert body["foods"][0]["nutrition_basis"] == "food_table"
        assert body["timing_ms"]["vision"] >= 0
        assert body["timing_ms"]["calibration"] >= 0
        assert body["timing_ms"]["total"] >= body["timing_ms"]["vision"]

    def test_recognize_food_creates_single_upload_photo_draft(
        self, client, db, auth_headers, tmp_path, monkeypatch
    ):
        from app.api import upload as upload_api
        from app.services.ai.food_recognition import food_recognition_service

        async def recognize(*_args, **_kwargs):
            return {
                "success": True,
                "foods": [{
                    "name": "牛肉面", "quantity": "1碗", "calories": 650,
                    "protein": 28, "carbs": 80, "fat": 18, "fiber": 4,
                    "confidence": 0.86,
                }],
                "total_calories": 650,
                "total_protein": 28,
                "total_carbs": 80,
                "total_fat": 18,
                "total_fiber": 4,
            }

        upload_root = tmp_path / "uploads"
        monkeypatch.setattr(food_recognition_service, "is_available", lambda: True)
        monkeypatch.setattr(food_recognition_service, "recognize_food_from_base64", recognize)
        monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(upload_root))

        response = client.post(
            "/api/v1/diet/recognize",
            json={
                "image_base64": VALID_PNG_BASE64,
                "image_type": "png",
                "create_photo_draft": True,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        token = response.json()["photo_draft_token"]
        assert token and len(token) >= 24
        draft = db.query(DietPhotoDraft).one()
        assert draft.token == token
        assert draft.status == "pending"
        assert draft.image_url.startswith(f"/api/v1/upload/files/diet/{draft.user_id}/")
        asset = db.query(DietPhotoAsset).one()
        assert asset.photo_draft_token == token
        assert asset.diet_record_id is None
        assert asset.lifecycle == "pending"
        assert asset.storage_key == draft.image_url
        assert len(list(upload_root.rglob("*.png"))) == 1

    def test_photo_draft_confirmation_reuses_image_and_is_idempotent(
        self, client, db, auth_headers, tmp_path, monkeypatch
    ):
        from app.api import upload as upload_api
        from app.services.ai.food_recognition import food_recognition_service

        async def recognize(*_args, **_kwargs):
            return {
                "success": True,
                "foods": [{
                    "name": "牛肉面", "quantity": "1碗", "calories": 650,
                    "protein": 28, "carbs": 80, "fat": 18, "fiber": 4,
                    "confidence": 0.86,
                }],
                "total_calories": 650,
                "total_protein": 28,
                "total_carbs": 80,
                "total_fat": 18,
                "total_fiber": 4,
            }

        upload_root = tmp_path / "uploads"
        monkeypatch.setattr(food_recognition_service, "is_available", lambda: True)
        monkeypatch.setattr(food_recognition_service, "recognize_food_from_base64", recognize)
        monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(upload_root))

        recognized = client.post(
            "/api/v1/diet/recognize",
            json={
                "image_base64": VALID_PNG_BASE64,
                "image_type": "png",
                "create_photo_draft": True,
            },
            headers=auth_headers,
        )
        token = recognized.json()["photo_draft_token"]
        payload = {
            "record_date": str(date.today()),
            "meal_type": "lunch",
            "food_items": "牛肉面 1碗",
            "calories": 650,
            "photo_draft_token": token,
            "ai_recognized": 1,
        }

        first = client.post("/api/v1/diet/records", json=payload, headers=auth_headers)
        second = client.post(
            "/api/v1/diet/records",
            json=payload,
            headers={**auth_headers, "Idempotency-Key": "different-client-retry-key"},
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert first.json()["image_url"]
        assert db.query(DietRecord).count() == 1
        asset = db.query(DietPhotoAsset).one()
        assert asset.diet_record_id == first.json()["id"]
        assert asset.photo_draft_token is None
        assert asset.lifecycle == "attached"
        assert len(list(upload_root.rglob("*.png"))) == 1
        assert db.query(DietPhotoDraft).count() == 0
        cancelled_after_confirm = client.delete(
            f"/api/v1/diet/photo-drafts/{token}",
            headers=auth_headers,
        )
        assert cancelled_after_confirm.status_code == 409

    def test_photo_draft_is_owner_scoped_and_cancel_removes_image(
        self, client, db, auth_headers, tmp_path, monkeypatch
    ):
        from app.api import upload as upload_api
        from app.services.ai.food_recognition import food_recognition_service
        from app.services.auth import auth_service

        async def recognize(*_args, **_kwargs):
            return {
                "success": True,
                "foods": [{"name": "苹果", "quantity": "1个", "calories": 80}],
                "total_calories": 80,
            }

        upload_root = tmp_path / "uploads"
        monkeypatch.setattr(food_recognition_service, "is_available", lambda: True)
        monkeypatch.setattr(food_recognition_service, "recognize_food_from_base64", recognize)
        monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(upload_root))
        response = client.post(
            "/api/v1/diet/recognize",
            json={
                "image_base64": VALID_PNG_BASE64,
                "image_type": "png",
                "create_photo_draft": True,
            },
            headers=auth_headers,
        )
        token = response.json()["photo_draft_token"]

        other = User(
            username="other-photo-user",
            email="other-photo@example.com",
            hashed_password="hashed",
            name="Other",
            is_active=True,
            is_approved=True,
        )
        db.add(other)
        db.commit()
        db.refresh(other)
        other_headers = {
            "Authorization": f"Bearer {auth_service.create_access_token({'sub': str(other.id)})}"
        }

        forbidden = client.delete(
            f"/api/v1/diet/photo-drafts/{token}",
            headers=other_headers,
        )
        cancelled = client.delete(
            f"/api/v1/diet/photo-drafts/{token}",
            headers=auth_headers,
        )

        assert forbidden.status_code == 404
        assert cancelled.status_code == 204
        assert db.query(DietPhotoDraft).count() == 0
        assert list(upload_root.rglob("*.png")) == []

    @pytest.mark.parametrize("recognized_name", ["沃克", "伏诺拉生", "保存并确认"])
    def test_recognize_and_save_rejects_non_food_model_output(
        self, client, db, auth_headers, tmp_path, monkeypatch, recognized_name
    ):
        from app.api import upload as upload_api
        from app.services.ai.food_recognition import food_recognition_service

        async def recognize(*_args, **_kwargs):
            return {
                "success": True,
                "foods": [{"name": recognized_name, "confidence": 0.9}],
                "total_calories": 10,
            }

        monkeypatch.setattr(food_recognition_service, "is_available", lambda: True)
        monkeypatch.setattr(food_recognition_service, "recognize_food_from_base64", recognize)
        monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(tmp_path / "uploads"))

        response = client.post(
            "/api/v1/diet/recognize-and-save",
            json={
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
                "image_type": "png",
                "record_date": str(date.today()),
                "meal_type": "lunch",
            },
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert db.query(DietRecord).count() == 0
        assert list((tmp_path / "uploads").rglob("*")) == []

    def test_recognize_and_save_image_failure_creates_no_record(
        self, client, db, auth_headers, tmp_path, monkeypatch
    ):
        from app.api import upload as upload_api
        from app.services.ai.food_recognition import food_recognition_service

        async def recognize(*_args, **_kwargs):
            return {
                "success": True,
                "foods": [{"name": "鸡胸肉", "confidence": 0.9}],
                "total_calories": 180,
            }

        blocked_root = tmp_path / "not-a-directory"
        blocked_root.write_text("occupied")
        monkeypatch.setattr(food_recognition_service, "is_available", lambda: True)
        monkeypatch.setattr(food_recognition_service, "recognize_food_from_base64", recognize)
        monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(blocked_root))

        response = client.post(
            "/api/v1/diet/recognize-and-save",
            json={
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
                "image_type": "png",
                "record_date": str(date.today()),
                "meal_type": "lunch",
            },
            headers=auth_headers,
        )

        assert response.status_code == 500
        assert db.query(DietRecord).count() == 0

    def test_recognize_and_save_db_failure_removes_written_image(
        self, client, db, auth_headers, tmp_path, monkeypatch
    ):
        from app.api import upload as upload_api
        from app.services.ai.food_recognition import food_recognition_service

        async def recognize(*_args, **_kwargs):
            return {
                "success": True,
                "foods": [{"name": "鸡胸肉", "confidence": 0.9}],
                "total_calories": 180,
            }

        upload_root = tmp_path / "uploads"
        monkeypatch.setattr(food_recognition_service, "is_available", lambda: True)
        monkeypatch.setattr(food_recognition_service, "recognize_food_from_base64", recognize)
        monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(upload_root))

        def fail_commit():
            raise RuntimeError("db down")

        monkeypatch.setattr(db, "commit", fail_commit)
        response = client.post(
            "/api/v1/diet/recognize-and-save",
            json={
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
                "image_type": "png",
                "record_date": str(date.today()),
                "meal_type": "lunch",
            },
            headers=auth_headers,
        )

        assert response.status_code == 500
        assert list(upload_root.rglob("*.png")) == []


class TestDietValidation:
    """饮食记录验证测试"""

    def test_meal_types(self, client, auth_headers):
        """测试所有餐类型"""
        meal_types = ["breakfast", "lunch", "dinner", "snack", "extra"]

        for meal_type in meal_types:
            data = {
                "record_date": str(date.today()),
                "meal_type": meal_type,
                "food_items": f"测试{meal_type}"
            }
            response = client.post(
                "/api/v1/diet/records",
                json=data,
                headers=auth_headers
            )
            assert response.status_code == 200, f"餐类型 {meal_type} 创建失败"

    def test_negative_calories(self, client, auth_headers):
        """测试负数热量（应该允许，可能有特殊情况）"""
        data = {
            "record_date": str(date.today()),
            "meal_type": "breakfast",
            "food_items": "测试",
            "calories": -100  # 负数
        }
        response = client.post(
            "/api/v1/diet/records",
            json=data,
            headers=auth_headers
        )
        # 根据业务需求，可能允许或不允许
        # 这里假设不做验证，允许保存
        assert response.status_code in [200, 422]

    def test_empty_food_items(self, client, auth_headers):
        """测试空食物列表"""
        data = {
            "record_date": str(date.today()),
            "meal_type": "breakfast",
            "food_items": ""  # 空字符串
        }
        response = client.post(
            "/api/v1/diet/records",
            json=data,
            headers=auth_headers
        )
        # 空字符串应该被允许（由前端验证）
        assert response.status_code == 200
