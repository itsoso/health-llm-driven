"""补剂管理API测试"""
import pytest
from datetime import date, timedelta
from app.models.supplement import SupplementRecord
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
