"""R17 引导式运动任务(readiness 门控 + 循证内容库)。

钉死五条裁决:
  ① GREEN → do 全量(默认 plan)
  ② RED + strength → rest_instead 且 exercise swap 成 stretch_basic(不在红灯推力量)
  ③ YELLOW → modified 减量(reps×0.7 / sets-1)
  ④ recovery_decision 失败 → 降级 unknown,不抛,保守按减量(modified)
  ⑤ API shape 200 + 顶层键齐全 + user_id 隔离(鉴权)

门控走 monkeypatch 注入 training_decision,确定性可测,不连真 readiness。
"""
import uuid

import pytest

import app.services.movement.guided_task as gt
from app.models.user import User


@pytest.fixture
def auth(client, db):
    user = User(username=f"m_{uuid.uuid4().hex[:6]}", email=f"m_{uuid.uuid4().hex[:6]}@x.com",
                hashed_password="x", name="m", is_active=True, is_approved=True)
    db.add(user); db.commit(); db.refresh(user)
    from app.services.auth import auth_service
    return user, {"Authorization": f"Bearer {auth_service.create_access_token({'sub': str(user.id)})}"}


def _patch_zone(monkeypatch, light, score=70, reasons=None):
    """注入 training_decision 返回值(zone 灯)。"""
    payload = {"light": light, "readiness_score": score, "reasons": reasons or [f"恢复 {light}"]}
    monkeypatch.setattr(
        "app.services.recovery_decision.training_decision",
        lambda db, uid: payload,
    )


# ── ① GREEN → do 全量 ────────────────────────────────────────────
def test_green_strength_is_do_full_plan(db, auth, monkeypatch):
    user, _ = auth
    _patch_zone(monkeypatch, "green", score=88)
    task = gt.build_guided_task(db, user.id, "strength")
    assert task["gate"]["decision"] == "do"
    assert task["gate"]["readiness_zone"] == "green"
    assert task["exercise"]["id"] == "pushup_standard"
    # 无历史 → 默认量 3×15
    assert task["plan"]["sets"] == 3 and task["plan"]["reps"] == 15
    assert task["safety_note"] is None
    assert "3×15" in task["title"]


# ── ② RED + strength → rest_instead + swap stretch ───────────────
def test_red_strength_swaps_to_stretch_rest_instead(db, auth, monkeypatch):
    user, _ = auth
    _patch_zone(monkeypatch, "red", score=35)
    task = gt.build_guided_task(db, user.id, "strength")
    assert task["gate"]["decision"] == "rest_instead"
    assert task["gate"]["readiness_zone"] == "red"
    assert task["exercise"]["id"] == "stretch_basic"   # swap,不推力量
    assert task["exercise"]["evidence_tier"] in ("A", "B", "C")
    assert task["safety_note"] is not None
    assert "拉伸" in task["title"]
    # 拉伸是时长型,无 reps
    assert task["plan"]["duration_sec"] and task["plan"]["reps"] is None


# ── ③ YELLOW → modified 减量 ──────────────────────────────────────
def test_yellow_strength_is_modified_reduced(db, auth, monkeypatch):
    user, _ = auth
    _patch_zone(monkeypatch, "yellow", score=60)
    task = gt.build_guided_task(db, user.id, "strength")
    assert task["gate"]["decision"] == "modified"
    assert task["gate"]["readiness_zone"] == "yellow"
    assert task["exercise"]["id"] == "pushup_standard"
    # 默认 3×15 → sets-1=2, reps×0.7=10
    assert task["plan"]["sets"] == 2
    assert task["plan"]["reps"] == 10
    assert task["safety_note"] is not None


# ── ④ recovery_decision 失败 → 降级不抛,保守 modified ───────────────
def test_decision_failure_degrades_to_conservative(db, auth, monkeypatch):
    user, _ = auth

    def _boom(db, uid):
        raise RuntimeError("readiness backend down")

    monkeypatch.setattr("app.services.recovery_decision.training_decision", _boom)
    task = gt.build_guided_task(db, user.id, "strength")   # 不应抛
    assert task["gate"]["readiness_zone"] == "unknown"
    # unknown 当 yellow 保守 → modified 减量,绝不在缺数据时全量推力量
    assert task["gate"]["decision"] == "modified"
    assert task["plan"]["sets"] == 2 and task["plan"]["reps"] == 10


def test_unknown_light_value_also_degrades(db, auth, monkeypatch):
    user, _ = auth
    # training_decision 返回非法 light(如 gray)→ 也走 unknown 保守
    monkeypatch.setattr(
        "app.services.recovery_decision.training_decision",
        lambda db, uid: {"light": "gray", "readiness_score": None, "reasons": []},
    )
    task = gt.build_guided_task(db, user.id, "strength")
    assert task["gate"]["readiness_zone"] == "unknown"
    assert task["gate"]["decision"] == "modified"


# ── 进阶:GREEN + 上次完成 → +2 reps ─────────────────────────────
def test_green_progression_bumps_reps_from_last_record(db, auth, monkeypatch):
    from datetime import date

    user, _ = auth
    from app.models.daily_health import ExerciseRecord
    db.add(ExerciseRecord(user_id=user.id, record_date=date.today(),
                          exercise_type="pushup_standard", reps=15, sets=3))
    db.commit()
    _patch_zone(monkeypatch, "green", score=90)
    task = gt.build_guided_task(db, user.id, "strength")
    assert task["gate"]["decision"] == "do"
    assert task["plan"]["reps"] == 17   # 15 + 2(完成且无 RPE)


def test_mobility_domain_green_is_stretch(db, auth, monkeypatch):
    user, _ = auth
    _patch_zone(monkeypatch, "green", score=85)
    task = gt.build_guided_task(db, user.id, "mobility")
    assert task["exercise"]["id"] == "stretch_basic"
    assert task["gate"]["decision"] == "do"


# ── ⑤ API shape + 鉴权 + user_id 隔离 ────────────────────────────
def test_api_guided_task_shape_200(client, auth, monkeypatch):
    _, headers = auth
    _patch_zone(monkeypatch, "green")
    r = client.get("/api/v1/movement/guided-task?domain=strength", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("domain", "gate", "title", "exercise", "plan",
                "voice_script", "capture", "safety_note"):
        assert key in body, f"missing top-level key: {key}"
    assert body["gate"]["decision"] in ("do", "modified", "rest_instead")
    assert body["capture"]["mode"] == "manual"
    assert "completed" in body["capture"]["fields"]


def test_api_guided_task_requires_auth(client):
    assert client.get("/api/v1/movement/guided-task").status_code == 401


def test_api_red_strength_swaps_via_http(client, auth, monkeypatch):
    _, headers = auth
    _patch_zone(monkeypatch, "red", score=30)
    r = client.get("/api/v1/movement/guided-task?domain=strength", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["gate"]["decision"] == "rest_instead"
    assert body["exercise"]["id"] == "stretch_basic"
