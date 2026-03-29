"""体检报告对比和指标分析端点测试"""
import pytest
from datetime import date
from tests.conftest import create_authenticated_user
from app.models.family_health import MedicalReport, MedicalIndicator


class TestCompareReports:
    """测试 GET /api/v1/family-health/medical-reports/compare"""

    def _create_reports_and_indicators(self, db, user_id):
        """创建 2 份测试报告及其指标"""
        r1 = MedicalReport(
            user_id=user_id,
            report_date=date(2025, 1, 15),
            hospital="测试医院A",
            report_type="blood",
            title="2025年1月血常规",
            status="completed",
            extracted_items=[{"name": "空腹血糖", "value": 5.8, "unit": "mmol/L"}],
        )
        r2 = MedicalReport(
            user_id=user_id,
            report_date=date(2025, 6, 15),
            hospital="测试医院B",
            report_type="blood",
            title="2025年6月血常规",
            status="completed",
            extracted_items=[{"name": "空腹血糖", "value": 6.2, "unit": "mmol/L"}],
        )
        db.add_all([r1, r2])
        db.commit()
        db.refresh(r1)
        db.refresh(r2)

        # 添加指标记录
        ind1 = MedicalIndicator(
            user_id=user_id,
            report_id=r1.id,
            name="空腹血糖",
            category="glucose",
            value=5.8,
            unit="mmol/L",
            reference_low=3.9,
            reference_high=6.1,
            is_abnormal=False,
            record_date=date(2025, 1, 15),
        )
        ind2 = MedicalIndicator(
            user_id=user_id,
            report_id=r2.id,
            name="空腹血糖",
            category="glucose",
            value=6.2,
            unit="mmol/L",
            reference_low=3.9,
            reference_high=6.1,
            is_abnormal=True,
            severity="mild",
            record_date=date(2025, 6, 15),
        )
        db.add_all([ind1, ind2])
        db.commit()
        return r1, r2

    def test_compare_two_reports(self, client, db):
        """对比 2 份报告，验证响应结构"""
        user, token = create_authenticated_user(db)
        headers = {"Authorization": f"Bearer {token}"}

        r1, r2 = self._create_reports_and_indicators(db, user.id)
        resp = client.get(
            f"/api/v1/family-health/medical-reports/compare?report_ids={r1.id},{r2.id}",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "reports" in data
        assert "indicators" in data
        assert "summary" in data
        assert len(data["reports"]) == 2

    def test_compare_single_report_fails(self, client, db):
        """只传 1 个 ID 应返回 400"""
        user, token = create_authenticated_user(db)
        headers = {"Authorization": f"Bearer {token}"}

        r1 = MedicalReport(
            user_id=user.id,
            report_date=date(2025, 1, 1),
            report_type="general",
            status="completed",
        )
        db.add(r1)
        db.commit()
        db.refresh(r1)

        resp = client.get(
            f"/api/v1/family-health/medical-reports/compare?report_ids={r1.id}",
            headers=headers,
        )
        assert resp.status_code == 400

    def test_compare_invalid_ids(self, client, db):
        """传入不存在的 ID 应返回 404"""
        user, token = create_authenticated_user(db)
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.get(
            "/api/v1/family-health/medical-reports/compare?report_ids=99999,99998",
            headers=headers,
        )
        assert resp.status_code == 404

    def test_compare_bad_format(self, client, db):
        """格式错误应返回 400"""
        user, token = create_authenticated_user(db)
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.get(
            "/api/v1/family-health/medical-reports/compare?report_ids=abc,def",
            headers=headers,
        )
        assert resp.status_code == 400

    def test_compare_no_auth(self, client):
        """无认证应返回 401"""
        resp = client.get(
            "/api/v1/family-health/medical-reports/compare?report_ids=1,2",
        )
        assert resp.status_code == 401


class TestIndicatorsAnalysis:
    """测试 GET /api/v1/family-health/medical-indicators/analysis"""

    def test_analysis_empty(self, client, db):
        """没有指标数据时返回空列表"""
        user, token = create_authenticated_user(db)
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.get(
            "/api/v1/family-health/medical-indicators/analysis",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "indicators" in data
        assert data["indicators"] == []

    def test_analysis_with_category(self, client, db):
        """带 category 过滤"""
        user, token = create_authenticated_user(db)
        headers = {"Authorization": f"Bearer {token}"}

        ind = MedicalIndicator(
            user_id=user.id,
            name="总胆固醇",
            category="lipid",
            value=5.5,
            unit="mmol/L",
            is_abnormal=False,
            record_date=date(2025, 3, 1),
        )
        db.add(ind)
        db.commit()

        resp = client.get(
            "/api/v1/family-health/medical-indicators/analysis?category=lipid",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["category"] == "lipid"
        assert len(data["indicators"]) >= 1

    def test_analysis_no_auth(self, client):
        """无认证应返回 401"""
        resp = client.get(
            "/api/v1/family-health/medical-indicators/analysis",
        )
        assert resp.status_code == 401
