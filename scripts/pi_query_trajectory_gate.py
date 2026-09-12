#!/usr/bin/env python3
"""Bounded live Pi/executor query regression using only local synthetic records.

Offline: python scripts/pi_query_trajectory_gate.py
Preflight: DATABASE_URL=postgresql://ROLE@localhost/reva_pi_eval_NAME python ... --preflight --database-name reva_pi_eval_NAME --user-id 1
Live: same environment plus --include-live-llm --model MODEL --output /tmp/report.json

Uses existing provider configuration and audited synthetic consent, never grants
consent or copies production data. This exercises AgentExecutor.run_stream, the
real Pi process, real selected model, policy and DB-backed query tools. It is not
a synthesis-only eval, a clinical answer-quality judge, or a deployment gate.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
VERSION = "pi-query-trajectories.v1"
FIXTURE_SOURCE = "pi_query_trajectory_v1"
CASES = (
    {"id": "oral_diet", "query": "今日我吃了啥", "facts": (("燕麦",),), "read": True},
    {"id": "dinner_advice", "query": "今天晚上我吃了什么？给我一些建议。", "facts": (("番茄",), ("建议", "可以", "适当", "注意")), "read": True},
    {"id": "daily_recap", "query": "给我今天总结", "facts": (("燕麦", "番茄"), ("睡眠", "睡了"), ("运动", "步数", "散步")), "read": True},
    {"id": "daily_recap_advice", "query": "给我今天总结，给我建议", "facts": (("燕麦", "番茄"), ("睡眠", "睡了"), ("建议", "可以", "注意")), "read": True},
    {"id": "quoted_advice", "query": "分析以下建议：\n如果家里有的话不用再买。出门前检查水杯和舒适的鞋，行程按自己的体力调整。", "facts": (), "read": False},
)
_FAILURE_NOTICES = ("这次查询未执行", "已停止这次查询", "未生成可发布", "请明确要查询哪类记录", "请明确查询日期")
RUNTIME_SOURCES = (
    "agent_executor.py", "agent_daily_read_execution.py", "agent_turn_outcome.py", "agent_input_tool_scope.py",
    "answer_evidence.py",
    "utterance_intent_classifier.py", "clinician_provenance_guard.py", "agent_kernel/capability_policy.py",
    "agent_kernel/health_semantics.py", "agent_kernel/daily_read_plan.py",
    "agent_kernel/tool_gateway.py",
)


def source_fingerprints() -> dict[str, str]:
    base = ROOT / "backend/app/services"
    return {path: hashlib.sha256((base / path).read_bytes()).hexdigest() for path in RUNTIME_SOURCES}


def validate_database_url(url: str, expected_name: str) -> None:
    parsed = urlsplit(url)
    if (parsed.scheme.split("+")[0] != "postgresql"
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.path.lstrip("/") != expected_name
            or not expected_name.startswith("reva_pi_eval_")
            or parse_qs(parsed.query)):
        raise ValueError("requires an explicitly named loopback PostgreSQL evaluation database without query overrides")


def score_case(case: dict, done: dict, answer: str, tools: list[str], *, unchanged: bool) -> dict:
    trace = done.get("kernel_trace") or {}
    outcome = done.get("turn_outcome") or {}
    basis = (done.get("answer_evidence") or {}).get("basis") or []
    basis_text = json.dumps(basis, ensure_ascii=False)
    checks = {
        "real_pi_kernel": (done.get("perf") or {}).get("agent_kernel") == "pi",
        "completed_generation": done.get("completion_status") == "complete",
        "successful_outcome": outcome.get("status") == "complete",
        "no_tool_failure": trace.get("tool_failures", 0) == 0 and trace.get("blocked_tools", 0) == 0,
        "publishable_answer": bool(answer.strip()) and not any(v in answer for v in _FAILURE_NOTICES),
        "query_evidence": not case["read"] or bool(
            tools and basis and any(term in basis_text for term in case["facts"][0])
        ),
        "expected_fact_coverage": all(any(term in answer for term in group) for group in case["facts"]),
        "health_data_unchanged": unchanged and not done.get("write_receipts"),
    }
    return {"passed": all(checks.values()), "checks": checks,
            "failed_checks": [name for name, passed in checks.items() if not passed]}


def terminal_event_data(event: dict) -> dict | None:
    if event.get("event") != "done":
        return None
    return event.get("data") or {}


def _preflight(args):
    database_url = os.environ.get("DATABASE_URL", "")
    validate_database_url(database_url, args.database_name)
    sys.path.insert(0, str(ROOT / "backend"))
    from sqlalchemy import text
    from app.config import settings
    from app.database import SessionLocal, engine
    from app.models.user import User
    from app.services.ai_consent import get_ai_consent, is_disclosed_model
    from app.services.llm.model_registry import get_model

    validate_database_url(engine.url.render_as_string(hide_password=False), args.database_name)
    api_host = urlsplit(settings.health_api_base_url or "http://localhost:8000").hostname
    if api_host not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("health API must point to loopback")
    if settings.agent_base_url:
        raise ValueError("direct agent endpoint bypasses the tracked provider path")
    if min(settings.tokenplan_user_daily_call_quota, settings.tokenplan_user_monthly_token_quota) <= 0:
        raise ValueError("configured provider quota guards must be active")
    with SessionLocal() as db:
        db.info["app_user_id"] = args.user_id
        role = db.execute(text("SELECT NOT rolsuper AND NOT rolbypassrls FROM pg_roles WHERE rolname=current_user")).scalar()
        if role is not True:
            raise ValueError("evaluation must use a restricted PostgreSQL role")
        user = db.query(User).filter(User.id == args.user_id).first()
        if user is None or not any(tag in (user.username or "").lower() for tag in ("synthetic", "eval")):
            raise ValueError("existing synthetic subject marker is required")
        if not get_ai_consent(db, args.user_id)["accepted"]:
            raise ValueError("existing audited synthetic AI consent is required")
        # Verify ledger readability now; do not discover missing quota access
        # after a paid call has already started.
        db.execute(text("SELECT count(*) FROM llm_usage_logs WHERE user_id=:uid"), {"uid": args.user_id}).scalar()
    for model in args.model:
        entry = get_model(model)
        if entry is None or not is_disclosed_model(entry):
            raise ValueError("selected model must exist and use a disclosed AI destination")
    return SessionLocal, engine


def _seed(db, user_id: int, today) -> None:
    from app.models.daily_health import DietRecord, ExerciseRecord, GarminData
    for meal, food, calories in (("breakfast", "合成早餐燕麦", 300), ("dinner", "合成晚餐番茄蛋饭", 420)):
        if not db.query(DietRecord).filter_by(user_id=user_id, record_date=today, source=FIXTURE_SOURCE, meal_type=meal).first():
            db.add(DietRecord(user_id=user_id, record_date=today, source=FIXTURE_SOURCE, meal_type=meal,
                              food_name=food, food_items=food, calories=calories))
    if not db.query(GarminData).filter_by(user_id=user_id, record_date=today, data_source=FIXTURE_SOURCE).first():
        db.add(GarminData(user_id=user_id, record_date=today, data_source=FIXTURE_SOURCE,
                          total_sleep_duration=420, sleep_score=80, steps=6000))
    if not db.query(ExerciseRecord).filter_by(user_id=user_id, record_date=today, notes=FIXTURE_SOURCE).first():
        db.add(ExerciseRecord(user_id=user_id, record_date=today, notes=FIXTURE_SOURCE,
                              exercise_type="散步", duration=30, intensity="低"))
    db.commit()


def _health_fingerprint(db, user_id: int) -> str:
    from app.models.daily_health import DietRecord, ExerciseRecord, GarminData
    payload = []
    for model in (DietRecord, ExerciseRecord, GarminData):
        rows = db.query(model).filter(model.user_id == user_id).order_by(model.id).all()
        payload.append([{column.name: getattr(row, column.name) for column in model.__table__.columns} for row in rows])
    return hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest()


def _save(path: Path, report: dict) -> None:
    # Metadata only. Neither configuration values nor response/source health
    # payloads are placed into stdout or the report.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)


async def _run(args, SessionLocal, engine) -> dict:
    import httpx
    from app.database import get_db
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.tool_registry import classify_tool_effect
    from app.services.ai_consent import ai_user_scope, is_disclosed_destination
    from app.services.auth import auth_service
    from app.services.llm import usage_tracker
    from app.twin import cache
    from app.utils import redis_cache

    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    report = {"version": VERSION, "fixture_date": str(today), "timezone": "Asia/Shanghai",
              "models": args.model, "cases": args.case or [c["id"] for c in CASES],
              "source_sha256": source_fingerprints(),
              "status": "running", "results": [], "provider_calls": 0}
    spent = {"calls": 0, "reserved_tokens": 0}
    safety_violations = []
    blocked_auxiliary_requests = []
    original_guard = usage_tracker._enforce_monthly_token_quota

    def bounded_guard(**kwargs):
        original_guard(**kwargs)
        estimated = usage_tracker._estimate_tokens(usage_tracker._messages_to_text(kwargs.get("messages") or []),
                                                   kwargs.get("model") or "gpt-4o-mini") + int(kwargs.get("max_tokens") or 0)
        if spent["calls"] >= args.max_calls or spent["reserved_tokens"] + estimated > args.max_reserved_tokens:
            raise usage_tracker.LLMBudgetExceeded(reason="synthetic_suite_budget_exceeded")
        spent["calls"] += 1
        spent["reserved_tokens"] += estimated

    with SessionLocal() as db:
        db.info["app_user_id"] = args.user_id
        _seed(db, args.user_id, today)
    usage_tracker.set_caller("pi_query_trajectory_synthetic", user_id=args.user_id)

    async def no_health_http(*_args, **_kwargs):
        safety_violations.append("health_http_forbidden")
        raise RuntimeError("synthetic_suite_health_http_forbidden")

    with ExitStack() as stack:
        # Existing caches may refer to a different local checkout's subject 1.
        # Disable only caches; consent, quotas, provider transport and execution
        # stay real. A fresh conversation is used for every case.
        stack.enter_context(patch.object(redis_cache, "get_redis_client", return_value=None))
        stack.enter_context(patch.object(cache, "get_cached_twin", return_value=None))
        stack.enter_context(patch.object(cache, "set_cached_twin", return_value=False))
        stack.enter_context(patch.object(cache, "invalidate_twin", return_value=None))
        stack.enter_context(patch.object(usage_tracker, "_enforce_monthly_token_quota", bounded_guard))
        stack.enter_context(patch.object(AgentExecutor, "_api_post", no_health_http))
        original_async_send, original_sync_send = httpx.AsyncClient.send, httpx.Client.send

        def egress_allowed(client, request):
            if is_disclosed_destination(str(request.url)):
                return True
            if isinstance(getattr(client, "_transport", None), httpx.ASGITransport):
                return True
            blocked_auxiliary_requests.append("external_auxiliary_data_unavailable")
            return False

        async def restricted_async_send(client, request, *positional, **kwargs):
            if not egress_allowed(client, request):
                raise RuntimeError("synthetic_suite_external_data_forbidden")
            return await original_async_send(client, request, *positional, **kwargs)

        def restricted_sync_send(client, request, *positional, **kwargs):
            if not egress_allowed(client, request):
                raise RuntimeError("synthetic_suite_external_data_forbidden")
            return original_sync_send(client, request, *positional, **kwargs)

        stack.enter_context(patch.object(httpx.AsyncClient, "send", restricted_async_send))
        stack.enter_context(patch.object(httpx.Client, "send", restricted_sync_send))
        from main import app

        def synthetic_db():
            with SessionLocal() as db:
                db.info["app_user_id"] = args.user_id
                yield db

        previous_overrides = dict(app.dependency_overrides)
        app.dependency_overrides[get_db] = synthetic_db
        stack.callback(lambda: (app.dependency_overrides.clear(), app.dependency_overrides.update(previous_overrides)))
        token = auth_service.create_access_token({"sub": str(args.user_id)})
        asgi_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://synthetic.local")
        original_get = AgentExecutor._api_get
        original_get_json = AgentExecutor._api_get_json

        def asgi_read(original):
            async def read(executor, url, headers):
                parsed = urlsplit(url)
                if (parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                        or parsed.path.rstrip("/") != "/api/v1/diet/records/me"
                        or headers.get("Authorization") != f"Bearer {token}"):
                    safety_violations.append({"kind": "asgi_read_boundary", "host": parsed.hostname,
                                              "path": parsed.path, "matching_auth": headers.get("Authorization") == f"Bearer {token}"})
                    return await no_health_http()
                old_client = executor._http_client
                executor._http_client = asgi_client
                try:
                    return await original(executor, url, headers)
                finally:
                    executor._http_client = old_client
            return read

        stack.enter_context(patch.object(AgentExecutor, "_api_get", asgi_read(original_get)))
        stack.enter_context(patch.object(AgentExecutor, "_api_get_json", asgi_read(original_get_json)))
        stack.enter_context(ai_user_scope(args.user_id))
        for model in args.model:
            for case in CASES:
                if args.case and case["id"] not in args.case:
                    continue
                result = {"case_id": case["id"], "requested_model": model}
                started = time.monotonic()
                with SessionLocal() as db:
                    db.info["app_user_id"] = args.user_id
                    before = _health_fingerprint(db, args.user_id)
                    executor = AgentExecutor(db)
                    dispatch = executor._dispatch_tool_request
                    tool_names = []

                    async def local_read_only(request, token):
                        if (request.tool_name not in {"health_query", "health_query_batch", "health_manage", "knowledge_search"}
                                or classify_tool_effect(request.tool_name, request.arguments) != "read"):
                            safety_violations.append("tool_forbidden")
                            raise RuntimeError("synthetic_suite_forbidden_tool")
                        tool_names.append(request.tool_name)
                        return await dispatch(request, token)

                    executor._dispatch_tool_request = local_read_only
                    done = {}
                    answer = ""
                    try:
                        async with asyncio.timeout(args.case_timeout):
                            async for event in executor.run_stream(args.user_id, case["query"],
                                    extra_context=json.dumps({"model_id": model}), read_only_tools=True,
                                    user_auth_token=token):
                                terminal = terminal_event_data(event)
                                if terminal is not None:
                                    done = terminal
                        if done.get("message_id"):
                            message = (db.query(AgentMessage).join(AgentConversation,
                                       AgentMessage.conversation_id == AgentConversation.id)
                                       .filter(AgentMessage.id == done["message_id"],
                                               AgentConversation.user_id == args.user_id).first())
                            answer = message.content if message else ""
                        db.expire_all()
                        unchanged = before == _health_fingerprint(db, args.user_id)
                        result.update(score_case(case, done, answer, tool_names, unchanged=unchanged))
                        if safety_violations:
                            result["passed"] = False
                            result["failed_checks"].append("synthetic_safety_boundary")
                            result["safety_violations"] = safety_violations[:]
                    except Exception as exc:
                        db.rollback()
                        result.update(passed=False, error_type=type(exc).__name__)
                    result.update(elapsed_ms=round((time.monotonic() - started) * 1000),
                                  answer_sha256=hashlib.sha256(answer.encode()).hexdigest(),
                                  tools=tool_names, actual_answer_model=done.get("answer_model"),
                                  actual_tool_models=done.get("tool_models"),
                                  completion_status=done.get("completion_status"),
                                  outcome_status=(done.get("turn_outcome") or {}).get("status"),
                                  goal_kind=(done.get("kernel_trace") or {}).get("goal_kind"),
                                  goal_satisfied=(done.get("kernel_trace") or {}).get("goal_satisfied"),
                                  evidence_count=len((done.get("answer_evidence") or {}).get("basis") or []))
                report["results"].append(result)
                report.update(provider_calls=spent["calls"], reserved_tokens=spent["reserved_tokens"],
                              blocked_auxiliary_request_count=len(blocked_auxiliary_requests))
                _save(args.output, report)
                print(json.dumps({"case_id": case["id"], "model": model, "passed": result["passed"]}), flush=True)
                if not result["passed"]:
                    report["status"] = "failed"
                    await asgi_client.aclose()
                    return report
        await asgi_client.aclose()
    report["source_unchanged"] = report["source_sha256"] == source_fingerprints()
    report["status"] = "passed" if report["source_unchanged"] else "source_changed"
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-live-llm", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--database-name", default="reva_pi_eval_20260912")
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--case", action="append", choices=[c["id"] for c in CASES], default=[])
    parser.add_argument("--max-calls", type=int, default=40)
    parser.add_argument("--max-reserved-tokens", type=int, default=600000)
    parser.add_argument("--case-timeout", type=int, default=120)
    parser.add_argument("--output", type=Path, default=Path("/tmp/reva-pi-query-trajectories.json"))
    args = parser.parse_args(argv)
    if not args.include_live_llm and not args.preflight:
        print(json.dumps({"version": VERSION, "status": "not_run", "cases": [c["id"] for c in CASES], "paid_calls": 0}))
        return 0
    try:
        if not (1 <= args.max_calls <= 100 and 1 <= args.max_reserved_tokens <= 2000000
                and 1 <= args.case_timeout <= 300 and 1 <= len(args.model) <= 3):
            raise ValueError("select 1-3 models and bounded positive call/token/time limits")
        SessionLocal, engine = _preflight(args)
        if args.preflight and not args.include_live_llm:
            print(json.dumps({"version": VERSION, "status": "preflight_passed", "paid_calls": 0}))
            return 0
        report = asyncio.run(_run(args, SessionLocal, engine))
        _save(args.output, report)
        return 0 if report["status"] == "passed" else 1
    except Exception as exc:
        print(json.dumps({"version": VERSION, "status": "blocked", "error_type": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
