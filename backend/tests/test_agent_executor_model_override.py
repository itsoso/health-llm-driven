import json
from datetime import date

from app.models.daily_health import DietRecord
from app.services.agent_executor import (
    _build_database_verification_snapshot,
    _extract_database_verification_instruction,
    _extract_desktop_response_instruction,
    _extract_model_id_from_extra_context,
)


def test_extract_model_id_from_mac_extra_context_accepts_registry_id():
    extra_context = json.dumps({
        "client": "mac",
        "model_id": "qwen3.6-plus",
    })

    assert _extract_model_id_from_extra_context(extra_context) == "qwen3.6-plus"


def test_extract_model_id_from_mac_extra_context_maps_provider_model_alias():
    extra_context = json.dumps({
        "client": "mac",
        "model_id": "commercial/Claude-Opus-4.7",
    })

    assert _extract_model_id_from_extra_context(extra_context) == "claude-opus-4.7"


def test_extract_model_id_from_extra_context_rejects_invalid_values():
    assert _extract_model_id_from_extra_context('{"model_id": "../bad"}') is None
    assert _extract_model_id_from_extra_context("not json") is None


def test_extract_desktop_response_instruction_from_extra_context():
    extra_context = json.dumps({
        "client": "mac",
        "desktop_markdown_response_instruction": "请用 Markdown 分段，不要输出密集长段落。",
    })

    assert _extract_desktop_response_instruction(extra_context) == "请用 Markdown 分段，不要输出密集长段落。"


def test_extract_desktop_response_instruction_requires_mac_client():
    extra_context = json.dumps({
        "client": "mobile",
        "desktop_markdown_response_instruction": "不要输出 markdown",
    })

    assert _extract_desktop_response_instruction(extra_context) is None


def test_extract_database_verification_instruction_requires_diet_query_from_db():
    extra_context = json.dumps({
        "from": "diet/post_confirm",
        "database_verification": {
            "required": True,
            "date": "2026-07-11",
            "verify_record_id": 89,
            "query_scope": "daily_diet_records",
            "totals_source": "database",
            "forbid_cached_totals": True,
            "missing_record_instruction": "如果数据库里查不到 verify_record_id 对应记录，明确提示同步失败。",
        },
    }, ensure_ascii=False)

    instruction = _extract_database_verification_instruction(extra_context)

    assert instruction is not None
    assert "health_query(dimension='diet')" in instruction
    assert "2026-07-11" in instruction
    assert "89" in instruction
    assert "不要使用入口上下文里的 totals" in instruction
    assert "同步失败" in instruction


def test_extract_database_verification_instruction_ignores_unrelated_context():
    assert _extract_database_verification_instruction("not json") is None
    assert _extract_database_verification_instruction(json.dumps({"from": "diet/today"})) is None


def test_build_database_verification_snapshot_reads_diet_records_from_db(db):
    db.add_all([
        DietRecord(
            id=89,
            user_id=7,
            record_date=date(2026, 7, 11),
            meal_type="lunch",
            food_items="鸡胸肉 200g + 糙米饭一碗",
            calories=560,
            protein=67,
            carbs=48,
            fat=9.2,
            fiber=3,
        ),
        DietRecord(
            id=90,
            user_id=7,
            record_date=date(2026, 7, 11),
            meal_type="dinner",
            food_items="番茄鸡蛋面",
            calories=420,
            protein=22,
            carbs=62,
            fat=10,
            fiber=4,
        ),
        DietRecord(
            id=91,
            user_id=8,
            record_date=date(2026, 7, 11),
            meal_type="lunch",
            food_items="其他用户午餐",
            calories=999,
        ),
    ])
    db.commit()
    extra_context = json.dumps({
        "database_verification": {
            "required": True,
            "date": "2026-07-11",
            "verify_record_id": 89,
            "query_scope": "daily_diet_records",
            "totals_source": "database",
        },
    })

    snapshot = _build_database_verification_snapshot(db, user_id=7, extra_context=extra_context)

    assert snapshot is not None
    assert "verify_record_id=89 存在: yes" in snapshot
    assert "总热量 980 kcal" in snapshot
    assert "蛋白质 89 g" in snapshot
    assert "id=89 | lunch | 鸡胸肉 200g + 糙米饭一碗 | 560 kcal" in snapshot
    assert "id=90 | dinner | 番茄鸡蛋面 | 420 kcal" in snapshot
    assert "其他用户午餐" not in snapshot


def test_build_database_verification_snapshot_reports_missing_record(db):
    db.add(DietRecord(
        id=90,
        user_id=7,
        record_date=date(2026, 7, 11),
        meal_type="dinner",
        food_items="番茄鸡蛋面",
        calories=420,
    ))
    db.commit()
    extra_context = json.dumps({
        "database_verification": {
            "required": True,
            "date": "2026-07-11",
            "verify_record_id": 89,
            "query_scope": "daily_diet_records",
            "totals_source": "database",
        },
    })

    snapshot = _build_database_verification_snapshot(db, user_id=7, extra_context=extra_context)

    assert snapshot is not None
    assert "verify_record_id=89 存在: no" in snapshot
    assert "同步失败" in snapshot
