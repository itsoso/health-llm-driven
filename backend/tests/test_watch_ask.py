"""Apple Watch one-shot ask endpoint safety contract.

The watch surface is intentionally tiny: short answer, no diagnosis, no
prescription, and fail-loud when safety screening is incomplete.
"""
import ast
import re
import uuid
from pathlib import Path

import pytest

import app.api.watch as watch_api
from app.models.user import User
from app.services.auth import auth_service

_ENDPOINT = "/api/v1/watch/ask"


def _mk_user(db) -> User:
    u = User(
        username=f"wa_{uuid.uuid4().hex[:6]}",
        email=f"wa_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="wa",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {auth_service.create_access_token({'sub': str(user.id)})}"}


async def _short_ok_answer(*_args, **_kwargs) -> str:
    return "今天先以轻量活动为主,如果明显不适就停止并改在 iPhone 查看详情。"


def _post(client, user, text, extra=None):
    payload = {"text": text}
    if extra:
        payload.update(extra)
    return client.post(_ENDPOINT, json=payload, headers=_headers(user))


def test_watch_ask_normal_short_answer(client, db, monkeypatch):
    user = _mk_user(db)
    monkeypatch.setattr(watch_api, "_generate_watch_ask_answer", _short_ok_answer, raising=False)

    r = _post(client, user, "我今天适合做轻量活动吗")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"].count("。") <= 2
    assert body["escalate_to_phone"] is False
    assert body["requires_medical_attention"] is False


def test_watch_ask_diagnostic_or_prescription_intent_escalates(client, db, monkeypatch):
    user = _mk_user(db)
    monkeypatch.setattr(watch_api, "_generate_watch_ask_answer", _short_ok_answer, raising=False)

    r = _post(client, user, "我胸痛是不是心梗,要不要吃药")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["escalate_to_phone"] is True
    assert body["requires_medical_attention"] is True
    assert re.search(r"iPhone|120|就医", body["answer"])
    assert not re.search(r"确诊|你患有|治愈|保证", body["answer"])


@pytest.mark.parametrize(
    "text",
    [
        "我这是感冒吗",
        "会不会是肺炎",
        "有没有可能是糖尿病",
        "要不要拍片",
        "布洛芬吃多少",
        "是否需要做核磁",
    ],
)
def test_watch_ask_common_medical_intents_escalate(client, db, monkeypatch, text):
    user = _mk_user(db)
    monkeypatch.setattr(watch_api, "_generate_watch_ask_answer", _short_ok_answer, raising=False)

    r = _post(client, user, text)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["escalate_to_phone"] is True
    assert re.search(r"iPhone|120|就医", body["answer"])


def test_watch_ask_evaluation_failure_is_fail_loud(client, db, monkeypatch):
    user = _mk_user(db)

    def _boom(_twin):
        raise RuntimeError("rule engine failed")

    monkeypatch.setattr(watch_api, "evaluate_rules_with_status", _boom)
    monkeypatch.setattr(watch_api, "_generate_watch_ask_answer", _short_ok_answer, raising=False)

    r = _post(client, user, "今天有点累")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["escalate_to_phone"] is True
    assert body["requires_medical_attention"] is True
    assert "本次未能完成自动安全筛查,请勿据此判断为安全;不适请就医,紧急拨 120" in body["answer"]


def test_watch_ask_partial_rule_failure_is_fail_loud(client, db, monkeypatch):
    user = _mk_user(db)

    def _partial_failure(_twin):
        return [], 1

    monkeypatch.setattr(watch_api, "evaluate_rules_with_status", _partial_failure)
    monkeypatch.setattr(watch_api, "_generate_watch_ask_answer", _short_ok_answer, raising=False)

    r = _post(client, user, "今天有点累")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["escalate_to_phone"] is True
    assert body["requires_medical_attention"] is True
    assert "本次未能完成自动安全筛查" in body["answer"]


def test_watch_ask_llm_failure_escalates_not_500(client, db, monkeypatch):
    user = _mk_user(db)

    async def _llm_boom(*_args, **_kwargs) -> str:
        raise RuntimeError("llm provider unavailable")

    monkeypatch.setattr(watch_api, "_generate_watch_ask_answer", _llm_boom, raising=False)

    r = _post(client, user, "我今天适合散步吗")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["escalate_to_phone"] is True
    assert body["requires_medical_attention"] is False
    assert "iPhone" in body["answer"]


def test_watch_ask_sanitizes_llm_guidance_output(client, db, monkeypatch):
    user = _mk_user(db)

    async def _bad_answer(*_args, **_kwargs) -> str:
        return "每天吃 50 克坚果,必须做满 3 组。"

    monkeypatch.setattr(watch_api, "_generate_watch_ask_answer", _bad_answer, raising=False)

    r = _post(client, user, "我今天怎么安排饮食和活动")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["escalate_to_phone"] is True
    assert "每天吃 50" not in body["answer"]
    assert "必须做满" not in body["answer"]


def test_watch_ask_blocks_diagnostic_or_medication_llm_output(client, db, monkeypatch):
    user = _mk_user(db)

    for unsafe in (
        "你可能是胃炎,可以吃布洛芬。",
        "可以服用对乙酰氨基酚。",
        "考虑上呼吸道感染。",
        "考虑急性胃炎，建议就医。",
        "建议服用奥司他韦。",
        "口服对乙酰氨基酚。",
        "服用奥司他韦。",
        "每日一片。",
        "每晚一粒。",
        "早晚各一粒。",
        "一次一片。",
        "使用布地奈德鼻喷雾。",
        "外用莫匹罗星。",
        "涂抹红霉素软膏。",
        "滴用左氧氟沙星滴眼液。",
    ):
        async def _bad_answer(*_args, **_kwargs) -> str:
            return unsafe

        monkeypatch.setattr(watch_api, "_generate_watch_ask_answer", _bad_answer, raising=False)

        r = _post(client, user, "胃有点不舒服")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["escalate_to_phone"] is True
        assert unsafe[:4] not in body["answer"]


def test_watch_ask_empty_llm_output_escalates_to_phone(client, db, monkeypatch):
    user = _mk_user(db)

    async def _empty_answer(*_args, **_kwargs) -> str:
        return "   "

    monkeypatch.setattr(watch_api, "_generate_watch_ask_answer", _empty_answer, raising=False)

    r = _post(client, user, "我今天适合散步吗")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["escalate_to_phone"] is True
    assert body["requires_medical_attention"] is False
    assert "iPhone" in body["answer"]


def test_watch_ask_uses_token_user_not_client_user_id(client, db, monkeypatch):
    user_a = _mk_user(db)
    user_b = _mk_user(db)
    seen = {}

    def _record_uid(_db, uid, _twin, _seen_sections, *, raise_on_error=False):
        seen["uid"] = uid

    monkeypatch.setattr(watch_api.builder, "_fill_problem_red_lines", _record_uid)
    monkeypatch.setattr(watch_api, "_generate_watch_ask_answer", _short_ok_answer, raising=False)

    r = _post(client, user_a, "我今天适合走路吗", extra={"user_id": user_b.id})

    assert r.status_code == 200, r.text
    assert seen["uid"] == user_a.id


@pytest.mark.parametrize("bad", ["", "   ", "问" * 501])
def test_watch_ask_invalid_text_400(client, db, bad):
    user = _mk_user(db)

    r = _post(client, user, bad)

    assert r.status_code == 400, r.text


def test_watch_ask_does_not_call_build_twin_ast():
    src = Path(watch_api.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    fn = next(
        (
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "watch_ask"
        ),
        None,
    )
    assert fn is not None, "未找到 watch_ask"

    called = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                called.add(f.id)
            elif isinstance(f, ast.Attribute):
                called.add(f.attr)
    assert "build_twin" not in called, f"watch_ask 不得调用 build_twin,实得调用 {called}"
