# -*- coding: utf-8 -*-
"""ProgramTemplate catalog and start contract."""

from app.models.health_program import HealthProgram


def test_program_template_catalog_contains_minimum_domains(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    resp = client.get("/api/v1/program-templates", headers=headers)

    assert resp.status_code == 200
    templates = resp.json()["templates"]
    ids = {template["id"] for template in templates}
    assert {"metabolic-reset-8w", "recovery-capacity-8w", "sleep-foundation-8w"}.issubset(ids)
    metabolic = next(template for template in templates if template["id"] == "metabolic-reset-8w")
    assert metabolic["version"] == "2026.06"
    assert metabolic["duration_weeks"] == 8
    assert "适用人群" in metabolic["review_checklist"]
    assert metabolic["claim_boundary"] == "ProgramTemplate 是行为和复测框架,不构成诊断或治疗方案。"


def test_start_program_from_template_creates_user_program(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    resp = client.post("/api/v1/program-templates/sleep-foundation-8w/start", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["template"]["id"] == "sleep-foundation-8w"
    assert body["program"]["program_type"] == "sleep"
    assert body["program"]["primary_metrics"] == ["sleep_score", "hrv", "rhr"]
    assert body["template_contract"]["safety_gates"] == ["red_flags", "sleep_disorder_screen", "medication_review"]
    assert body["claim_boundary"] == "从模板创建的 Program 仍需按个人数据和医生建议调整。"

    program = db.query(HealthProgram).filter_by(user_id=user.id).one()
    assert program.name == "睡眠基础 8 周项目"
    assert program.target["template_id"] == "sleep-foundation-8w"
    assert program.target["version"] == "2026.06"


def test_start_program_from_template_is_idempotent(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    first = client.post("/api/v1/program-templates/metabolic-reset-8w/start", headers=headers).json()
    second = client.post("/api/v1/program-templates/metabolic-reset-8w/start", headers=headers).json()

    assert first["program"]["id"] == second["program"]["id"]
    assert db.query(HealthProgram).filter_by(user_id=user.id).count() == 1
