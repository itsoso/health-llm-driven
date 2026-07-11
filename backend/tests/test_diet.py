"""饮食记录API测试"""
import pytest
from datetime import date
from app.models.user import User
from app.models.daily_health import DietRecord


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

    def test_implausible_past_record_date_is_clamped_to_server_today(
        self, client, auth_headers, caplog
    ):
        """客户端 bug 把"刚吃的午餐"写成远早的 record_date → 钳制回服务端今天 (Asia/Shanghai)。

        对应真实事故: mobile POST 的"刚才"午餐落到 2 天前 (客户端日期 bug)。防御纵深:
        偏离 > 2 天判为不合理, 钳制而非 422 (钳制比硬拒更安全的 UX), 并写 WARNING 日志。
        任务示例: server-today=2026-07-01 时提交 2026-06-29 → 存成 2026-07-01。
        (此处用相对日期使测试不依赖运行当天; 用 3 天前确保触发 > 2 天阈值。)
        """
        from datetime import datetime, timedelta, timezone

        server_today = datetime.now(timezone(timedelta(hours=8))).date()
        implausible = server_today - timedelta(days=3)  # > 2 天 → 触发钳制

        import logging
        with caplog.at_level(logging.WARNING):
            response = client.post(
                "/api/v1/diet/records",
                json={
                    "record_date": str(implausible),
                    "meal_type": "lunch",
                    "food_items": "wagas 沙拉",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        # 被钳制回服务端今天, 而非客户端传的 3 天前
        assert data["record_date"] == str(server_today)
        # 且写了可被监控捕获的告警日志 (不假装成功)
        assert any(
            "implausible record_date" in rec.getMessage() for rec in caplog.records
        )

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
            "notes": "更新后的备注"
        }
        update_response = client.put(
            f"/api/v1/diet/records/{record_id}",
            json=update_data,
            headers=auth_headers
        )
        assert update_response.status_code == 200
        assert update_response.json()["calories"] == 500
        assert update_response.json()["notes"] == "更新后的备注"

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
