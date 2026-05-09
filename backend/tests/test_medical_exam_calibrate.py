"""Calibrate UI — PATCH /medical-exams/items/{id} 单测.

覆盖:
  1. 校正 value → 同步到 medical_indicators
  2. 第一次校正快照原值到 original_value
  3. 越权 (改别人的 exam item) → 403
  4. 不存在 → 404
  5. is_abnormal 改成 normal → indicator.is_abnormal=False
"""
from __future__ import annotations

from datetime import date

import pytest

from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.models.family_health import MedicalIndicator


def _create_exam_with_ocr_item(db, user_id):
    exam = MedicalExam(
        user_id=user_id,
        exam_date=date(2026, 5, 1),
        exam_type="comprehensive",
        notes="从图片 OCR 导入: lab.jpg",
    )
    db.add(exam)
    db.flush()

    item = MedicalExamItem(
        exam_id=exam.id,
        item_name="低密度脂蛋白",
        item_code="LDL",
        value=12.0,  # OCR 抽错: 实际是 4.1, 看错小数点
        unit="mmol/L",
        reference_range="< 3.4",
        is_abnormal="high",
        source="ocr",
        original_value=12.0,
    )
    db.add(item)

    indicator = MedicalIndicator(
        user_id=user_id,
        exam_id=exam.id,
        name="低密度脂蛋白",
        item_code="LDL",
        value=12.0,
        unit="mmol/L",
        reference_range="< 3.4",
        is_abnormal=True,
        record_date=exam.exam_date,
        source="image_ocr",
    )
    db.add(indicator)
    db.commit()
    db.refresh(item)
    return exam, item, indicator


def test_patch_item_updates_value_and_indicator(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    _, item, _ = _create_exam_with_ocr_item(db, user.id)

    res = client.patch(
        f"/api/v1/medical-exams/items/{item.id}",
        json={"value": 4.1, "is_abnormal": "high"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["value"] == 4.1
    assert body["manually_corrected_at"] is not None
    # original_value 第一次校正前已经在 OCR 写入时设为 12.0; 不应被覆盖
    assert body["original_value"] == 12.0

    db.expire_all()
    indicator = db.query(MedicalIndicator).filter_by(item_code="LDL").first()
    assert indicator.value == 4.1
    assert indicator.is_abnormal is True


def test_patch_item_first_correction_snapshots_original(client, db, auth_user_and_headers):
    """模拟 manual 创建的 item (无 original_value) 第一次校正 — 应快照原值."""
    user, headers = auth_user_and_headers
    exam = MedicalExam(user_id=user.id, exam_date=date(2026, 5, 1), exam_type="comprehensive")
    db.add(exam)
    db.flush()
    item = MedicalExamItem(
        exam_id=exam.id, item_name="尿酸", item_code="UA",
        value=380.0, unit="μmol/L", is_abnormal="normal", source="manual",
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    res = client.patch(
        f"/api/v1/medical-exams/items/{item.id}",
        json={"value": 420.0, "is_abnormal": "high"},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["value"] == 420.0
    assert body["original_value"] == 380.0  # 快照成功


def test_patch_item_is_normal_resets_indicator_flag(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    _, item, _ = _create_exam_with_ocr_item(db, user.id)

    res = client.patch(
        f"/api/v1/medical-exams/items/{item.id}",
        json={"is_abnormal": "normal"},
        headers=headers,
    )
    assert res.status_code == 200

    db.expire_all()
    indicator = db.query(MedicalIndicator).filter_by(item_code="LDL").first()
    assert indicator.is_abnormal is False


def test_patch_item_other_user_forbidden(client, db, auth_user_and_headers):
    """A 用户尝试改 B 用户的 exam item → 403."""
    user_b, _ = auth_user_and_headers

    # 创建另一个用户 + 他的 exam
    from app.models.user import User
    user_a = User(
        wechat_openid="other_a", username="user_a", phone="13900000099",
        name="User A", hashed_password="x", is_active=True, is_approved=True,
    )
    db.add(user_a)
    db.commit()
    _, item_a, _ = _create_exam_with_ocr_item(db, user_a.id)

    res = client.patch(
        f"/api/v1/medical-exams/items/{item_a.id}",
        json={"value": 1.0},
        headers=auth_user_and_headers[1],  # user_b 的 token
    )
    assert res.status_code == 403


def test_patch_nonexistent_item_returns_404(client, auth_user_and_headers):
    _, headers = auth_user_and_headers
    res = client.patch(
        "/api/v1/medical-exams/items/999999",
        json={"value": 1.0},
        headers=headers,
    )
    assert res.status_code == 404
