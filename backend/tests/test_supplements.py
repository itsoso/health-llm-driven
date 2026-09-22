"""补剂管理API测试"""
import pytest
from datetime import date, timedelta
from sqlalchemy import event

from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.user import User


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(
        username="suppuser",
        email="supp@example.com",
        hashed_password="hashed_password",
        name="补剂测试用户",
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
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_supplement_definition(test_user):
    """示例补剂定义数据"""
    return {
        "user_id": test_user.id,
        "name": "维生素D",
        "dosage": "1000IU",
        "timing": "morning",
        "description": "促进钙吸收",
        "is_active": True
    }


class TestSupplementDefinitionAPI:
    """补剂定义API测试类"""

    def test_create_supplement(self, client, auth_headers, sample_supplement_definition):
        """测试创建补剂"""
        response = client.post(
            "/api/v1/supplements/definitions",
            json=sample_supplement_definition,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "维生素D"
        assert data["dosage"] == "1000IU"
        assert "id" in data

    def test_create_supplement_minimal(self, client, auth_headers, test_user):
        """测试创建最小补剂（只有必填字段）"""
        minimal_data = {
            "user_id": test_user.id,
            "name": "鱼油"
        }
        response = client.post(
            "/api/v1/supplements/definitions",
            json=minimal_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "鱼油"

    def test_get_user_supplements(self, client, auth_headers, sample_supplement_definition, test_user):
        """测试获取用户补剂列表"""
        # 先创建补剂
        client.post(
            "/api/v1/supplements/definitions",
            json=sample_supplement_definition,
            headers=auth_headers
        )

        # 获取列表
        response = client.get(
            f"/api/v1/supplements/definitions/user/{test_user.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_my_supplements(self, client, auth_headers, sample_supplement_definition):
        """测试获取我的补剂列表"""
        # 先创建补剂
        client.post(
            "/api/v1/supplements/definitions",
            json=sample_supplement_definition,
            headers=auth_headers
        )

        # 获取列表
        response = client.get(
            "/api/v1/supplements/me/definitions",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_update_supplement(self, client, auth_headers, sample_supplement_definition):
        """测试更新补剂"""
        # 先创建补剂
        create_response = client.post(
            "/api/v1/supplements/definitions",
            json=sample_supplement_definition,
            headers=auth_headers
        )
        supplement_id = create_response.json()["id"]

        # 更新补剂
        update_data = {
            "dosage": "2000IU",
            "notes": "冬季加量"
        }
        update_response = client.put(
            f"/api/v1/supplements/definitions/{supplement_id}",
            json=update_data,
            headers=auth_headers
        )
        assert update_response.status_code == 200
        assert update_response.json()["dosage"] == "2000IU"

    def test_delete_supplement(self, client, auth_headers, sample_supplement_definition):
        """测试删除补剂"""
        # 先创建补剂
        create_response = client.post(
            "/api/v1/supplements/definitions",
            json=sample_supplement_definition,
            headers=auth_headers
        )
        supplement_id = create_response.json()["id"]

        # 删除补剂
        delete_response = client.delete(
            f"/api/v1/supplements/definitions/{supplement_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200


class TestSupplementRecordAPI:
    """补剂记录API测试类"""

    def test_create_supplement_record_requires_auth(self, client, sample_supplement_definition, auth_headers, test_user):
        """单条补剂打卡必须登录,不能信任请求体 user_id。"""
        create_response = client.post(
            "/api/v1/supplements/definitions",
            json=sample_supplement_definition,
            headers=auth_headers,
        )
        supplement_id = create_response.json()["id"]

        response = client.post(
            "/api/v1/supplements/records",
            json={
                "supplement_id": supplement_id,
                "user_id": test_user.id,
                "record_date": str(date.today()),
                "taken": True,
            },
        )
        assert response.status_code in (401, 403)

    def test_create_supplement_record(self, client, auth_headers, sample_supplement_definition, test_user):
        """测试创建补剂打卡记录"""
        # 先创建补剂
        create_response = client.post(
            "/api/v1/supplements/definitions",
            json=sample_supplement_definition,
            headers=auth_headers
        )
        supplement_id = create_response.json()["id"]

        # 创建打卡记录
        record_data = {
            "supplement_id": supplement_id,
            "user_id": test_user.id,
            "record_date": str(date.today()),
            "taken": True,
            "notes": "按时服用"
        }
        response = client.post(
            "/api/v1/supplements/records",
            json=record_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["taken"] == True
        assert data["user_id"] == test_user.id

    def test_create_supplement_record_ignores_forged_user_id(self, client, auth_headers, sample_supplement_definition, test_user):
        """单条打卡用当前登录用户,忽略请求体伪造的 user_id。"""
        create_response = client.post(
            "/api/v1/supplements/definitions",
            json=sample_supplement_definition,
            headers=auth_headers,
        )
        supplement_id = create_response.json()["id"]

        response = client.post(
            "/api/v1/supplements/records",
            json={
                "supplement_id": supplement_id,
                "user_id": test_user.id + 999,
                "record_date": str(date.today()),
                "taken": True,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["user_id"] == test_user.id

    def test_batch_checkin_rejects_other_users_supplement(self, client, db, auth_headers, sample_supplement_definition):
        """批量打卡必须校验 supplement_id 属于当前用户。"""
        create_response = client.post(
            "/api/v1/supplements/definitions",
            json=sample_supplement_definition,
            headers=auth_headers,
        )
        foreign_supplement_id = create_response.json()["id"]

        other = User(
            username="suppother",
            email="suppother@example.com",
            hashed_password="hashed_password",
            name="另一个用户",
            is_active=True,
            is_approved=True,
        )
        db.add(other)
        db.commit()
        db.refresh(other)

        from app.services.auth import auth_service
        other_headers = {
            "Authorization": f"Bearer {auth_service.create_access_token({'sub': str(other.id)})}"
        }

        response = client.post(
            "/api/v1/supplements/records/batch",
            json={
                "record_date": str(date.today()),
                "checkins": [{"supplement_id": foreign_supplement_id, "taken": True}],
            },
            headers=other_headers,
        )
        assert response.status_code == 404
        assert db.query(SupplementRecord).filter(
            SupplementRecord.supplement_id == foreign_supplement_id,
            SupplementRecord.record_date == date.today(),
        ).count() == 0

    def test_batch_checkin_rejects_bool_supplement_id(self, client, auth_headers):
        """bool 是 Python int 子类,但不能被当作 supplement_id。"""
        response = client.post(
            "/api/v1/supplements/records/batch",
            json={
                "record_date": str(date.today()),
                "checkins": [{"supplement_id": True, "taken": True}],
            },
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_batch_checkin(self, client, auth_headers, sample_supplement_definition, test_user):
        """测试批量打卡"""
        # 创建多个补剂
        supplements = []
        for name in ["维生素C", "锌片", "益生菌"]:
            data = sample_supplement_definition.copy()
            data["name"] = name
            response = client.post(
                "/api/v1/supplements/definitions",
                json=data,
                headers=auth_headers
            )
            supplements.append(response.json()["id"])

        # 批量打卡
        batch_data = {
            "user_id": test_user.id,
            "record_date": str(date.today()),
            "checkins": [{"supplement_id": sid, "taken": True} for sid in supplements]
        }
        response = client.post(
            "/api/v1/supplements/records/batch",
            json=batch_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 3

    def test_atomic_intake_batch_records_actual_dosage_and_is_idempotent(
        self, client, db, auth_headers, test_user
    ):
        payload = {
            "record_date": str(date.today()),
            "taken_time": "08:30:00",
            "items": [
                {"supplement_name": "Mitoq", "dosage": "2粒"},
                {"supplement_name": "叶酸", "dosage": "1粒"},
                {"supplement_name": "NAC", "dosage": "十二粒"},
            ],
        }

        first = client.post(
            "/api/v1/supplements/records/intake-batch",
            json=payload,
            headers=auth_headers,
        )
        second = client.post(
            "/api/v1/supplements/records/intake-batch",
            json=payload,
            headers=auth_headers,
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["record_ids"] == second.json()["record_ids"]
        assert first.json()["operation_id"] == second.json()["operation_id"]
        assert first.json()["operation_id"].startswith("supplement-batch:")
        assert [(item["supplement_name"], item["dosage"]) for item in first.json()["items"]] == [
            ("Mitoq", "2粒"),
            ("叶酸", "1粒"),
            ("NAC", "十二粒"),
        ]
        records = db.query(SupplementRecord).filter(
            SupplementRecord.user_id == test_user.id,
            SupplementRecord.record_date == date.today(),
        ).order_by(SupplementRecord.id).all()
        assert [record.actual_dosage for record in records] == ["2粒", "1粒", "十二粒"]
        assert len(records) == 3

    def test_atomic_intake_batch_keeps_regimen_dosage_separate_from_actual(
        self, client, db, auth_headers, test_user
    ):
        definitions = [
            SupplementDefinition(user_id=test_user.id, name="Mitoq", dosage=None, is_active=True),
            SupplementDefinition(user_id=test_user.id, name="叶酸", dosage="1粒", is_active=True),
            SupplementDefinition(user_id=test_user.id, name="NAC", dosage="2粒", is_active=True),
        ]
        db.add_all(definitions)
        db.commit()

        response = client.post(
            "/api/v1/supplements/records/intake-batch",
            json={
                "record_date": str(date.today()),
                "items": [
                    {"supplement_name": "Mitoq", "dosage": "2粒"},
                    {"supplement_name": "叶酸", "dosage": "1粒"},
                    {"supplement_name": "NAC", "dosage": "1粒"},
                ],
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        db.expire_all()
        assert [definition.dosage for definition in definitions] == [None, "1粒", "2粒"]
        records = db.query(SupplementRecord).filter(
            SupplementRecord.user_id == test_user.id
        ).order_by(SupplementRecord.id).all()
        assert [record.actual_dosage for record in records] == ["2粒", "1粒", "1粒"]

    @pytest.mark.parametrize("failing_item", (1, 2, 3))
    def test_atomic_intake_batch_rolls_back_every_item_on_mid_write_failure(
        self, client, db, auth_headers, test_user, failing_item
    ):
        inserted = 0

        def fail_on_target(_mapper, _connection, _target):
            nonlocal inserted
            inserted += 1
            if inserted == failing_item:
                raise RuntimeError("injected supplement record failure")

        event.listen(SupplementRecord, "before_insert", fail_on_target)
        try:
            response = client.post(
                "/api/v1/supplements/records/intake-batch",
                json={
                    "record_date": str(date.today()),
                    "items": [
                        {"supplement_name": "Mitoq", "dosage": "2粒"},
                        {"supplement_name": "叶酸", "dosage": "1粒"},
                        {"supplement_name": "NAC", "dosage": "1粒"},
                    ],
                },
                headers=auth_headers,
            )
        finally:
            event.remove(SupplementRecord, "before_insert", fail_on_target)

        assert response.status_code == 500
        assert db.query(SupplementRecord).filter(
            SupplementRecord.user_id == test_user.id
        ).count() == 0
        assert db.query(SupplementDefinition).filter(
            SupplementDefinition.user_id == test_user.id
        ).count() == 0

    def test_atomic_intake_batch_is_tenant_scoped(self, client, db, auth_headers, test_user):
        other = User(
            username="suppforeign",
            email="suppforeign@example.com",
            hashed_password="hashed_password",
            name="外部用户",
            is_active=True,
            is_approved=True,
        )
        db.add(other)
        db.flush()
        db.add(SupplementDefinition(user_id=other.id, name="Mitoq", dosage="9粒", is_active=True))
        db.commit()

        response = client.post(
            "/api/v1/supplements/records/intake-batch",
            json={
                "record_date": str(date.today()),
                "items": [
                    {"supplement_name": "Mitoq", "dosage": "2粒"},
                    {"supplement_name": "NAC", "dosage": "1粒"},
                ],
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert db.query(SupplementDefinition).filter(
            SupplementDefinition.user_id == test_user.id
        ).count() == 2
        assert db.query(SupplementRecord).filter(
            SupplementRecord.user_id == other.id
        ).count() == 0

    @pytest.mark.parametrize("duplicate", [False, True])
    def test_batch_name_conflict_is_prewrite_and_owner_scoped(
        self, client, db, auth_headers, test_user, duplicate,
    ):
        name = "合成营养素甲" if duplicate else "合成营养素甲增强版"
        db.add(SupplementDefinition(user_id=test_user.id, name=name, dosage="1粒", is_active=True))
        if duplicate:
            db.add(SupplementDefinition(user_id=test_user.id, name=name, dosage="2粒", is_active=True))
        other = User(username="conflict-other", name="合成其他用户", hashed_password="synthetic", is_active=True)
        db.add(other)
        db.flush()
        db.add(SupplementDefinition(user_id=other.id, name="合成营养素甲他人私有", is_active=True))
        db.commit()
        before = db.query(SupplementDefinition).count()
        response = client.post("/api/v1/supplements/records/intake-batch", headers=auth_headers,
            json={"record_date": str(date.today()), "items": [
                {"supplement_name": "新合成营养素乙", "dosage": "1粒"},
                {"supplement_name": "合成营养素甲", "dosage": "1粒"},
            ]})
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["dispatch_started"] is False
        assert detail["error_code"] == (
            "supplement_definition_ambiguous" if duplicate else "supplement_name_ambiguous"
        )
        assert set(detail["candidates"]) == {name}
        assert db.query(SupplementDefinition).count() == before
        assert db.query(SupplementRecord).count() == 0

    def test_get_supplements_with_status(self, client, auth_headers, sample_supplement_definition, test_user):
        """测试获取补剂及打卡状态"""
        # 创建补剂
        create_response = client.post(
            "/api/v1/supplements/definitions",
            json=sample_supplement_definition,
            headers=auth_headers
        )
        supplement_id = create_response.json()["id"]

        # 打卡
        record_data = {
            "supplement_id": supplement_id,
            "user_id": test_user.id,
            "record_date": str(date.today()),
            "taken": True
        }
        client.post(
            "/api/v1/supplements/records",
            json=record_data,
            headers=auth_headers
        )

        # 获取补剂及状态
        today = str(date.today())
        response = client.get(
            f"/api/v1/supplements/me/date/{today}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_update_and_delete_my_supplement_record(self, client, db, auth_headers, sample_supplement_definition, test_user):
        """补剂打卡记录必须可由 agent undo/update, 且只作用于当前用户。"""
        create_response = client.post(
            "/api/v1/supplements/definitions",
            json=sample_supplement_definition,
            headers=auth_headers,
        )
        supplement_id = create_response.json()["id"]
        record_response = client.post(
            "/api/v1/supplements/records",
            json={
                "supplement_id": supplement_id,
                "user_id": test_user.id,
                "record_date": str(date.today()),
                "taken": True,
                "notes": "已服用",
            },
            headers=auth_headers,
        )
        record_id = record_response.json()["id"]

        update = client.put(
            f"/api/v1/supplements/records/{record_id}",
            json={"taken": False, "notes": "误记,撤回"},
            headers=auth_headers,
        )
        assert update.status_code == 200
        assert update.json()["taken"] is False
        assert update.json()["notes"] == "误记,撤回"

        delete = client.delete(f"/api/v1/supplements/records/{record_id}", headers=auth_headers)
        assert delete.status_code == 200
        assert db.query(SupplementRecord).filter(SupplementRecord.id == record_id).count() == 0

    def test_supplement_record_update_delete_are_scoped_to_current_user(self, client, db, auth_headers):
        """不能通过 record_id 修改/删除其他用户的补剂打卡。"""
        other = User(
            username="supp_record_other",
            email="supp-record-other@example.com",
            hashed_password="hashed_password",
            name="另一个用户",
            is_active=True,
            is_approved=True,
        )
        db.add(other)
        db.commit()
        db.refresh(other)
        from app.models.supplement import SupplementDefinition

        other_supp = SupplementDefinition(user_id=other.id, name="鱼油", is_active=True)
        db.add(other_supp)
        db.commit()
        db.refresh(other_supp)
        other_record = SupplementRecord(
            user_id=other.id,
            supplement_id=other_supp.id,
            record_date=date.today(),
            taken=True,
            notes="other",
        )
        db.add(other_record)
        db.commit()
        db.refresh(other_record)

        update = client.put(
            f"/api/v1/supplements/records/{other_record.id}",
            json={"taken": False},
            headers=auth_headers,
        )
        delete = client.delete(
            f"/api/v1/supplements/records/{other_record.id}",
            headers=auth_headers,
        )

        assert update.status_code == 404
        assert delete.status_code == 404
        db.refresh(other_record)
        assert other_record.taken is True

    def test_get_my_stats(self, client, auth_headers, sample_supplement_definition):
        """测试获取我的补剂统计"""
        # 创建补剂
        client.post(
            "/api/v1/supplements/definitions",
            json=sample_supplement_definition,
            headers=auth_headers
        )

        # 获取统计
        response = client.get(
            "/api/v1/supplements/me/stats?days=7",
            headers=auth_headers
        )
        assert response.status_code == 200


class TestSupplementValidation:
    """补剂验证测试"""

    def test_duplicate_record_same_day(self, client, auth_headers, sample_supplement_definition, test_user):
        """测试同一天重复打卡（应更新或忽略）"""
        # 创建补剂
        create_response = client.post(
            "/api/v1/supplements/definitions",
            json=sample_supplement_definition,
            headers=auth_headers
        )
        supplement_id = create_response.json()["id"]

        # 第一次打卡
        record_data = {
            "supplement_id": supplement_id,
            "user_id": test_user.id,
            "record_date": str(date.today()),
            "taken": True
        }
        response1 = client.post(
            "/api/v1/supplements/records",
            json=record_data,
            headers=auth_headers
        )
        assert response1.status_code == 200

        # 同一天再次打卡（应该更新或返回已存在）
        record_data["notes"] = "补充打卡"
        response2 = client.post(
            "/api/v1/supplements/records",
            json=record_data,
            headers=auth_headers
        )
        # 根据具体实现，可能返回200或409
        assert response2.status_code in [200, 409]

    def test_multiple_supplements(self, client, auth_headers, test_user):
        """测试创建多个补剂"""
        supplements = ["维生素A", "维生素B", "维生素C", "维生素D", "维生素E"]

        for name in supplements:
            data = {
                "user_id": test_user.id,
                "name": name,
                "timing": "morning"
            }
            response = client.post(
                "/api/v1/supplements/definitions",
                json=data,
                headers=auth_headers
            )
            assert response.status_code == 200

        # 验证全部创建成功
        response = client.get(
            "/api/v1/supplements/me/definitions",
            headers=auth_headers
        )
        assert len(response.json()) >= 5
