"""血压记录API测试"""
import pytest
from datetime import date, timedelta
from app.models.user import User


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(
        username="bpuser",
        email="bp@example.com",
        hashed_password="hashed_password",
        name="血压测试用户",
        is_active=True,
        is_approved=True,
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


def _bp_data(test_user, systolic=120, diastolic=80, pulse=None, record_date=None, notes=None):
    """构建血压数据"""
    data = {
        "user_id": test_user.id,
        "record_date": record_date or str(date.today()),
        "systolic": systolic,
        "diastolic": diastolic,
    }
    if pulse is not None:
        data["pulse"] = pulse
    if notes:
        data["notes"] = notes
    return data


@pytest.fixture
def sample_bp_data(test_user):
    """示例血压数据"""
    return _bp_data(test_user, 120, 80, pulse=72, notes="晨起测量")


class TestBloodPressureAPI:
    """血压记录API测试类"""

    def test_create_bp_record(self, client, auth_headers, sample_bp_data):
        """测试创建血压记录"""
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=sample_bp_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["systolic"] == 120
        assert data["diastolic"] == 80
        assert data["pulse"] == 72
        assert "id" in data
        assert "category" in data

    def test_create_bp_record_minimal(self, client, auth_headers, test_user):
        """测试创建最小血压记录（只有收缩压和舒张压）"""
        minimal_data = _bp_data(test_user, 115, 75)
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=minimal_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["systolic"] == 115
        assert data["diastolic"] == 75
        assert data["pulse"] is None

    def test_bp_classification_normal(self, client, auth_headers, test_user):
        """测试血压分类 - 正常"""
        data = _bp_data(test_user, 115, 75)
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=data,
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["category"] == "正常"

    def test_bp_classification_elevated(self, client, auth_headers, test_user):
        """测试血压分类 - 正常偏高"""
        data = _bp_data(test_user, 125, 78)
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=data,
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["category"] == "正常偏高"

    def test_bp_classification_stage1(self, client, auth_headers, test_user):
        """测试血压分类 - 高血压1级"""
        data = _bp_data(test_user, 145, 92)
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=data,
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["category"] == "高血压1级"

    def test_get_my_bp_records(self, client, auth_headers, sample_bp_data):
        """测试获取我的血压记录"""
        client.post(
            "/api/v1/blood-pressure/records",
            json=sample_bp_data,
            headers=auth_headers
        )

        response = client.get(
            "/api/v1/blood-pressure/records/me",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_my_bp_stats(self, client, auth_headers, sample_bp_data):
        """测试获取我的血压统计"""
        client.post(
            "/api/v1/blood-pressure/records",
            json=sample_bp_data,
            headers=auth_headers
        )

        response = client.get(
            "/api/v1/blood-pressure/records/me/stats?days=30",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "average_systolic" in data or "total_records" in data

    def test_bp_trend(self, client, auth_headers, test_user):
        """测试血压趋势（多天数据）"""
        bp_data = [
            (120, 80), (118, 78), (125, 82), (122, 79), (119, 77)
        ]
        for i, (sys, dia) in enumerate(bp_data):
            data = _bp_data(test_user, sys, dia, record_date=str(date.today() - timedelta(days=i)))
            response = client.post(
                "/api/v1/blood-pressure/records",
                json=data,
                headers=auth_headers
            )
            assert response.status_code == 200

        response = client.get(
            "/api/v1/blood-pressure/records/me?limit=10",
            headers=auth_headers
        )
        assert response.status_code == 200
        records = response.json()
        assert len(records) >= 5

    def test_unauthorized_access(self, client, sample_bp_data):
        """测试未授权访问"""
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=sample_bp_data
        )
        assert response.status_code == 401


class TestBloodPressureValidation:
    """血压记录验证测试"""

    def test_missing_systolic(self, client, auth_headers, test_user):
        """测试缺少收缩压"""
        data = {"user_id": test_user.id, "record_date": str(date.today()), "diastolic": 80}
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=data,
            headers=auth_headers
        )
        assert response.status_code == 422

    def test_missing_diastolic(self, client, auth_headers, test_user):
        """测试缺少舒张压"""
        data = {"user_id": test_user.id, "record_date": str(date.today()), "systolic": 120}
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=data,
            headers=auth_headers
        )
        assert response.status_code == 422

    def test_negative_bp(self, client, auth_headers, test_user):
        """测试负数血压"""
        data = _bp_data(test_user, -120, 80)
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=data,
            headers=auth_headers
        )
        assert response.status_code in [200, 422]

    def test_systolic_less_than_diastolic(self, client, auth_headers, test_user):
        """测试收缩压小于舒张压"""
        data = _bp_data(test_user, 70, 90)
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=data,
            headers=auth_headers
        )
        assert response.status_code in [200, 422]


class TestBloodPressureClassification:
    """血压分类逻辑测试"""

    def test_all_classifications(self, client, auth_headers, test_user):
        """测试所有血压分类"""
        test_cases = [
            ((110, 70), "正常"),
            ((125, 78), "正常偏高"),
            ((135, 85), "高血压前期"),
            ((150, 95), "高血压1级"),
            ((170, 105), "高血压2级"),
            ((172, 112), "高血压3级"),
            # ≥180/120 不再折叠进 3级 —— 急症有立即就医语义 (Safety Guardian 同源)
            ((185, 115), "高血压急症"),
        ]

        for i, ((sys, dia), expected_category) in enumerate(test_cases):
            data = _bp_data(test_user, sys, dia, record_date=str(date.today() - timedelta(days=i+10)))
            response = client.post(
                "/api/v1/blood-pressure/records",
                json=data,
                headers=auth_headers
            )
            assert response.status_code == 200
            actual_category = response.json()["category"]
            assert actual_category == expected_category, \
                f"血压 {sys}/{dia} 应分类为 '{expected_category}'，实际为 '{actual_category}'"


class TestBloodPressureCrisisTier:
    """急症档 + 取高档语义 (纯函数, 不走 API)。

    背景: 旧实现 (a) 无急症档, ≥180/120 折叠进"高血压3级"丢失立即就医语义;
    (b) elif 链用 or, 单侧极高值被另一侧正常值拉低 (190/85 → "高血压前期")。
    两者都是 under-alarm 方向的洞。
    """

    def test_crisis_by_systolic_only(self):
        from app.utils.blood_pressure import classify_blood_pressure
        # 旧 bug: 190/85 → "高血压前期" (dia 85<90 让 or 链提前命中)
        assert classify_blood_pressure(190, 85) == "高血压急症"

    def test_crisis_by_diastolic_only(self):
        from app.utils.blood_pressure import classify_blood_pressure
        assert classify_blood_pressure(120, 125) == "高血压急症"

    def test_crisis_boundaries_inclusive(self):
        from app.utils.blood_pressure import classify_blood_pressure
        assert classify_blood_pressure(180, 80) == "高血压急症"   # sys 恰在阈值
        assert classify_blood_pressure(130, 120) == "高血压急症"  # dia 恰在阈值
        assert classify_blood_pressure(179, 119) == "高血压3级"   # 双双差 1 → 3级

    def test_take_higher_grade_semantics(self):
        from app.utils.blood_pressure import classify_blood_pressure
        # 旧 or 链会把这些全部降档 (under-alarm)
        assert classify_blood_pressure(165, 95) == "高血压2级"   # 旧: 1级
        assert classify_blood_pressure(150, 85) == "高血压1级"   # 旧: 前期
        assert classify_blood_pressure(145, 75) == "高血压1级"   # 旧: 前期
        assert classify_blood_pressure(125, 95) == "高血压1级"   # dia 定档
        assert classify_blood_pressure(170, 112) == "高血压3级"  # dia 110-119 → 3级

    def test_lower_bands_unchanged(self):
        from app.utils.blood_pressure import classify_blood_pressure
        assert classify_blood_pressure(110, 70) == "正常"
        assert classify_blood_pressure(125, 78) == "正常偏高"
        assert classify_blood_pressure(118, 85) == "高血压前期"  # ACC/AHA dia 80-89
        assert classify_blood_pressure(135, 85) == "高血压前期"

    def test_tighten_only_full_grid(self):
        """全网格回归: 新分级对任意输入只升不降 (加层不减层的量化版)。"""
        from app.utils.blood_pressure import classify_blood_pressure

        def _legacy(systolic, diastolic):
            if systolic < 120 and diastolic < 80:
                return "正常"
            elif systolic < 130 and diastolic < 80:
                return "正常偏高"
            elif systolic < 140 or diastolic < 90:
                return "高血压前期"
            elif systolic < 160 or diastolic < 100:
                return "高血压1级"
            elif systolic < 180 or diastolic < 110:
                return "高血压2级"
            else:
                return "高血压3级"

        rank = {
            "正常": 0, "正常偏高": 1, "高血压前期": 2,
            "高血压1级": 3, "高血压2级": 4, "高血压3级": 5, "高血压急症": 6,
        }
        for sys_bp in range(80, 221, 3):
            for dia_bp in range(40, 141, 3):
                new = classify_blood_pressure(sys_bp, dia_bp)
                old = _legacy(sys_bp, dia_bp)
                assert rank[new] >= rank[old], (
                    f"{sys_bp}/{dia_bp}: 新分级 '{new}' 低于旧分级 '{old}' (禁止降档)"
                )

    def test_crisis_threshold_same_source_as_safety_guardian(self):
        """急症阈值与 Safety Guardian vitals.bp_hypertensive_crisis 行为同源:
        规则命中 ⟺ 分级为急症 (阈值漂移时本测试红)。"""
        from datetime import datetime

        from app.agents.safety_guardian.rules.vitals import bp_hypertensive_crisis
        from app.twin.schema import HealthTwin, LabsContext, TwinMeta
        from app.utils.blood_pressure import classify_blood_pressure

        for sys_bp, dia_bp in [
            (179, 119), (180, 119), (179, 120), (180, 120),
            (185, 115), (120, 125), (200, 130), (150, 95),
        ]:
            twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
            twin.labs = LabsContext(
                blood_pressure_systolic=sys_bp, blood_pressure_diastolic=dia_bp
            )
            rule_fired = bp_hypertensive_crisis(twin) is not None
            is_crisis = classify_blood_pressure(sys_bp, dia_bp) == "高血压急症"
            assert rule_fired == is_crisis, (
                f"{sys_bp}/{dia_bp}: 规则命中={rule_fired} 但分级急症={is_crisis} (阈值漂移)"
            )

    def test_model_property_delegates_to_canonical(self):
        """models.BloodPressureRecord.category 不再是粗粒度副本 (desktop API 消费此路径)。"""
        from app.models.blood_pressure import BloodPressureRecord

        rec = BloodPressureRecord(systolic=185, diastolic=122)
        assert rec.category == "高血压急症"
        rec2 = BloodPressureRecord(systolic=150, diastolic=85)
        assert rec2.category == "高血压1级"


class TestBpReadPathCrisisWarning:
    """读查询路径确定性急症提示 (append_bp_crisis_read_warning 纯函数)。

    补 under-alarm 缺口: evaluate_safety 只在 health_record 写路径后运行,
    查询「看看我的血压」时库里躺着 185/122 不会触发任何 ⚠️ 提示。
    """

    def _records(self, *pairs, category=True):
        import json as _json

        from app.utils.blood_pressure import classify_blood_pressure

        out = []
        for i, (s, d) in enumerate(pairs):
            r = {"record_date": f"2026-07-{12 - i:02d}", "systolic": s, "diastolic": d}
            if category:
                r["category"] = classify_blood_pressure(s, d)
            out.append(r)
        return _json.dumps(out, ensure_ascii=False)

    def test_marker_drift_guard(self):
        """marker 必须与 agent_executor 单一真源一致 (漂移 = query_readouts 短路失守)。"""
        from app.services.agent_executor import SAFETY_WARNING_MARKER as EXEC_MARKER
        from app.utils.blood_pressure import SAFETY_WARNING_MARKER

        assert SAFETY_WARNING_MARKER == EXEC_MARKER

    def test_crisis_latest_appends_warning_with_reading_and_date(self):
        from app.utils.blood_pressure import (
            SAFETY_WARNING_MARKER,
            append_bp_crisis_read_warning,
        )

        result = self._records((185, 122), (130, 82))
        out = append_bp_crisis_read_warning(result)
        assert out.startswith(result)  # 原文一字不动, 只追加 (加层不减层)
        assert SAFETY_WARNING_MARKER in out
        assert "185/122 mmHg" in out
        assert "2026-07-12" in out
        assert "就医" in out

    def test_crisis_in_older_record_still_warns(self):
        from app.utils.blood_pressure import (
            SAFETY_WARNING_MARKER,
            append_bp_crisis_read_warning,
        )

        result = self._records((128, 82), (190, 95))
        out = append_bp_crisis_read_warning(result)
        assert SAFETY_WARNING_MARKER in out
        assert "190/95 mmHg" in out

    def test_numeric_crisis_without_category_still_warns(self):
        """fail-closed 双判: category 字段缺失/改名也不漏 (数字本身过阈值)。"""
        from app.utils.blood_pressure import (
            SAFETY_WARNING_MARKER,
            append_bp_crisis_read_warning,
        )

        result = self._records((182, 100), category=False)
        out = append_bp_crisis_read_warning(result)
        assert SAFETY_WARNING_MARKER in out

    def test_non_crisis_unchanged(self):
        from app.utils.blood_pressure import append_bp_crisis_read_warning

        result = self._records((150, 95), (128, 82))
        assert append_bp_crisis_read_warning(result) == result

    def test_error_and_empty_unchanged(self):
        from app.utils.blood_pressure import append_bp_crisis_read_warning

        assert append_bp_crisis_read_warning("") == ""
        err = "Error: 上游超时"
        assert append_bp_crisis_read_warning(err) == err

    def test_existing_marker_not_duplicated(self):
        from app.utils.blood_pressure import (
            SAFETY_WARNING_MARKER,
            append_bp_crisis_read_warning,
        )

        result = self._records((185, 122)) + SAFETY_WARNING_MARKER + " 既有告警"
        out = append_bp_crisis_read_warning(result)
        assert out == result
        assert out.count(SAFETY_WARNING_MARKER) == 1

    def test_truncation_note_suffix_still_detected(self):
        """_api_get 的"仅显示前N条"尾注不破坏检测 (raw_decode 合法前缀)。"""
        from app.utils.blood_pressure import (
            SAFETY_WARNING_MARKER,
            append_bp_crisis_read_warning,
        )

        result = self._records((186, 118)) + "\n...(仅显示前10条)"
        out = append_bp_crisis_read_warning(result)
        assert SAFETY_WARNING_MARKER in out

    def test_unparseable_text_with_crisis_word_generic_warning(self):
        """JSON 解析不出但文本带急症分级词 → 泛化提示 (under-alarm 宁多勿漏)。"""
        from app.utils.blood_pressure import (
            SAFETY_WARNING_MARKER,
            append_bp_crisis_read_warning,
        )

        text = "最近一次: 高血压急症 {截断"
        out = append_bp_crisis_read_warning(text)
        assert SAFETY_WARNING_MARKER in out
        assert out.startswith(text)

    def test_unparseable_text_without_crisis_word_unchanged(self):
        from app.utils.blood_pressure import append_bp_crisis_read_warning

        text = "一切正常 {截断"
        assert append_bp_crisis_read_warning(text) == text

    def test_lab_indicator_single_shape_detected(self):
        """query_lab_indicators 单指标 shape ({items:[...]}) 的血压桥接项同样检出。"""
        import json as _json

        from app.utils.blood_pressure import (
            SAFETY_WARNING_MARKER,
            append_bp_crisis_read_warning,
        )

        payload = {
            "count": 2,
            "metric_key": "blood_pressure",
            "source": "blood_pressure_records",
            "items": [
                {"name": "血压", "systolic": 186, "diastolic": 118,
                 "category": "高血压急症", "record_date": "2026-07-11",
                 "components": [
                     {"name": "收缩压", "value": 186}, {"name": "舒张压", "value": 118},
                 ]},
                {"name": "血压", "systolic": 128, "diastolic": 82,
                 "category": "高血压前期", "record_date": "2026-07-01"},
            ],
        }
        out = append_bp_crisis_read_warning(_json.dumps(payload, ensure_ascii=False))
        assert SAFETY_WARNING_MARKER in out
        assert "186/118 mmHg" in out

    def test_lab_indicator_batch_shape_detected(self):
        """query_lab_indicators 批量 shape ({by_name:{...}}) 嵌套也检出。"""
        import json as _json

        from app.utils.blood_pressure import (
            SAFETY_WARNING_MARKER,
            append_bp_crisis_read_warning,
        )

        payload = {
            "batch": True, "count": 1, "queried": ["血压", "LDL"],
            "by_name": {
                "血压": {"count": 1, "items": [
                    {"systolic": 181, "diastolic": 99, "record_date": "2026-07-10"},
                ]},
                "LDL": {"count": 0, "items": []},
            },
            "truncated": False,
        }
        out = append_bp_crisis_read_warning(_json.dumps(payload, ensure_ascii=False))
        assert SAFETY_WARNING_MARKER in out
        assert "181/99 mmHg" in out

    def test_lab_indicator_non_bp_shape_untouched(self):
        """非血压化验 shape (无 systolic/diastolic 键) 零命中零改动。"""
        import json as _json

        from app.utils.blood_pressure import append_bp_crisis_read_warning

        payload = {"count": 1, "items": [
            {"name": "LDL-C", "value": 4.9, "unit": "mmol/L", "is_abnormal": True},
        ]}
        raw = _json.dumps(payload, ensure_ascii=False)
        assert append_bp_crisis_read_warning(raw) == raw
