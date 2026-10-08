"""Bounded synthetic Pi/Gateway A/B. Never imported by application runtime.

This evaluates a fixed model and read task, not routing or clinical noninferiority.
Only disposable in-memory SQLite is accepted. Provider/tool failures stop the
sample instead of being hidden by application recovery. Consent remains real.
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack, aclosing
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4

REFERENCE_NOW = datetime.fromisoformat("2026-09-13T23:30:00+08:00")
VARIANTS = ("baseline", "p1", "p2", "combined", "empty_terminal", "evidence_compact", "runtime_preplan", "runtime_legacy_layout")
ANSWER_DIAGNOSTIC_CHAR_LIMIT = 16000


class BenchmarkStopped(BaseException):
    """Escape ordinary application fallback without making another paid call."""


@dataclass
class CallBudget:
    limit: int
    used: int = 0

    def reserve(self):
        if self.used >= self.limit:
            raise BenchmarkStopped("call_budget")
        self.used += 1


@dataclass
class ToolBudget:
    """Bound logical work separately from the runtime's one transient retry."""
    model_proposals: int = 0
    logical_executions: int = 0
    physical_dispatches: int = 0
    current_dispatches: int = 0

    def reserve_proposals(self, count):
        self.model_proposals += count
        if self.model_proposals > 3:
            raise BenchmarkStopped("model_tool_proposal_budget")

    def begin_execution(self):
        if self.logical_executions >= 3:
            raise BenchmarkStopped("logical_tool_budget")
        self.logical_executions += 1
        self.current_dispatches = 0

    def reserve_dispatch(self):
        if self.physical_dispatches >= 6 or self.current_dispatches >= 2:
            raise BenchmarkStopped("physical_tool_budget")
        if not self.logical_executions:
            raise BenchmarkStopped("dispatch_without_logical_execution")
        self.physical_dispatches += 1
        self.current_dispatches += 1


@dataclass(frozen=True)
class Scenario:
    id: str
    days: int
    state: str
    request_text: str | None = None
    allow_knowledge: bool = False
    dense_records: bool = False
    rich_profile: bool = False

    @property
    def query(self):
        return self.request_text or f"分析我最近{self.days}天的睡眠和饮食记录。"


SCENARIOS = tuple(Scenario("owned_read_7d_" + state, 7, state)
                  for state in ("available", "empty", "read_failure")) + tuple(
    Scenario("owned_lookup_7d_" + state, 7, state,
             "查询我最近7天的睡眠和饮食记录。")
    for state in ("available", "empty", "read_failure")
) + (
    # Separate from the strict read screen: analysis may legitimately retrieve
    # reviewed knowledge. Retain the original screen and its failed evidence.
    Scenario("analysis_7d_available", 7, "available", allow_knowledge=True),
    Scenario("analysis_7d_empty", 7, "empty", allow_knowledge=True),
    Scenario("analysis_7d_read_failure", 7, "read_failure", allow_knowledge=True),
    Scenario("analysis_7d_holdout", 7, "available",
             "复盘我最近7天的睡眠和饮食记录。", allow_knowledge=True),
    Scenario("analysis_7d_dense", 7, "available", allow_knowledge=True, dense_records=True),
    Scenario("analysis_31d_dense", 31, "available", allow_knowledge=True, dense_records=True),
    Scenario("analysis_1d_rich", 1, "available", allow_knowledge=True, rich_profile=True),
    Scenario("analysis_31d_rich", 31, "available", allow_knowledge=True, rich_profile=True),
)


def require_ephemeral(db):
    from app.config import settings
    bind = db.get_bind()
    url = getattr(bind, "engine", bind).url
    if settings.app_env != "test" or url.get_backend_name() != "sqlite" or url.database not in (None, "", ":memory:"):
        raise RuntimeError("full_task_eval_requires_test_in_memory_database")


def seed_synthetic_records(db, user_id, scenario):
    require_ephemeral(db)
    from app.models.user import User
    from app.models.daily_health import GarminData, DietRecord
    if scenario.rich_profile:
        from app.models.user_profile import UserProfile
        profile = db.query(UserProfile).filter_by(user_id=user_id).one_or_none()
        if profile is None:
            profile = UserProfile(user_id=user_id)
            db.add(profile)
        profile.height_cm, profile.current_weight_kg = 167, 49
        profile.allergies = ["花生"]
        profile.chronic_conditions = ["慢性肾病"]
        profile.current_medications = [{"name": "合成长期处方", "dosage": "未知", "frequency": "未知"}]
        db.flush()
    other = User(name="Synthetic other owner", email=f"other-{uuid4().hex}@example.invalid")
    db.add(other)
    db.flush()
    today = REFERENCE_NOW.date()
    db.add_all([
        GarminData(user_id=other.id, record_date=today, sleep_score=99, total_sleep_duration=599),
        GarminData(user_id=user_id, record_date=today + timedelta(days=1), sleep_score=11, total_sleep_duration=111),
    ])
    if scenario.state != "empty" and scenario.dense_records:
        for offset in range(scenario.days):
            day = today - timedelta(days=offset)
            db.add_all([
                GarminData(user_id=user_id, record_date=day, sleep_score=80, total_sleep_duration=420),
                DietRecord(user_id=user_id, record_date=day, meal_type="dinner",
                           food_name="合成番茄", food_items="合成番茄", calories=200),
            ])
        # A distinct same-name row with unknown energy: no deduplication or
        # imputation from its otherwise matching neighbour is permitted.
        db.add(DietRecord(user_id=user_id, record_date=today, meal_type="dinner",
                          food_name="合成番茄", food_items="合成番茄", calories=None))
    elif scenario.state != "empty":
        db.add_all([
            GarminData(user_id=user_id, record_date=today, sleep_score=80, total_sleep_duration=420),
            DietRecord(user_id=user_id, record_date=today - timedelta(days=1), meal_type="dinner",
                       food_name="合成番茄", food_items="合成番茄", calories=200),
        ])
    db.commit()


def health_digest(db):
    from app.models.daily_health import GarminData, DietRecord
    payload = {model.__tablename__: [
        {column.name: getattr(row, column.name) for column in model.__table__.columns}
        for row in db.query(model).order_by(model.id).all()
    ] for model in (GarminData, DietRecord)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class MeasuredProvider:
    provider_name = "bounded-eval"

    def __init__(self, factory, model, budget, calls, *, live, tool_budget=None, preserve_controls=False):
        self.factory, self.model, self.budget, self.calls, self.live = factory, model, budget, calls, live
        self.tool_budget = tool_budget or ToolBudget()
        self.preserve_controls = preserve_controls

    async def chat(self, **kwargs):
        raise BenchmarkStopped("unexpected_nonstream_call")

    async def chat_stream(self, **kwargs):
        from app.services.llm.usage_tracker import begin_usage_capture, end_usage_capture, summarize_usage_capture
        if self.preserve_controls:
            maximum = kwargs.get("max_tokens")
            if type(maximum) is not int or not 1 <= maximum <= 8000:
                raise BenchmarkStopped("output_budget")
            wire = {**kwargs, "return_metadata": True, "stream_options": {"include_usage": True}}
        else:
            wire = {**kwargs, "model": None, "temperature": 0, "max_tokens": min(int(kwargs.get("max_tokens") or 1200), 1200),
                    "return_metadata": True, "stream_options": {"include_usage": True}}
        payload = json.dumps(wire, ensure_ascii=False, sort_keys=True, default=str).encode()
        if len(payload) > 262144:
            raise BenchmarkStopped("input_budget")
        if len(self.calls) >= 3:
            raise BenchmarkStopped("sample_call_budget")
        self.budget.reserve()
        row = {"call_index": self.budget.used, "payload_sha256": hashlib.sha256(payload).hexdigest(),
               "input_bytes": len(payload), "phase": "tools" if kwargs.get("tools") else "answer",
               "token_source": "unknown" if self.live else "synthetic", "input_tokens": None,
               "output_tokens": None, "cached_tokens": None, "first_content_seconds": None,
               "answer_text": None if kwargs.get("tools") else "", "answer_text_truncated": False,
               "first_event_seconds": None, "first_reasoning_seconds": None,
               "last_event_seconds": None, "last_event_type": None,
               "event_counts": {"reasoning": 0, "content": 0, "tool_calls": 0, "finish": 0, "other": 0},
               "request_controls": {key: wire[key] for key in
                   ("temperature", "max_tokens", "thinking_budget", "enable_thinking")
                   if key in wire and type(wire[key]) in (bool, int, float)}}
        self.calls.append(row)
        capture = begin_usage_capture()
        started, finish = perf_counter(), None
        finish_event, finishes, proposals = None, 0, 0
        try:
            async with asyncio.timeout(45):
                async with aclosing(self.factory().chat_stream(**wire)) as stream:
                    async for event in stream:
                        event_seconds = perf_counter() - started
                        event_type = event.get("type")
                        event_type = event_type if event_type in row["event_counts"] else "other"
                        if row["first_event_seconds"] is None:
                            row["first_event_seconds"] = event_seconds
                        row["last_event_seconds"] = event_seconds
                        row["last_event_type"] = event_type
                        row["event_counts"][event_type] += 1
                        if event_type == "reasoning" and row["first_reasoning_seconds"] is None:
                            row["first_reasoning_seconds"] = event_seconds
                        # Keep timing/counts only for reasoning; never retain its text.
                        # This harness admits only disposable synthetic data.
                        # Keep visible answer content before output guards for
                        # diagnosing BLOCK vs false positives. Never capture
                        # reasoning events, requests, credentials or exceptions.
                        if event.get("type") == "content" and row["answer_text"] is not None:
                            text = event.get("text") or ""
                            remaining = ANSWER_DIAGNOSTIC_CHAR_LIMIT - len(row["answer_text"])
                            row["answer_text"] += text[:remaining]
                            row["answer_text_truncated"] |= len(text) > remaining
                        if event.get("type") == "content" and (event.get("text") or "").strip() and row["first_content_seconds"] is None:
                            row["first_content_seconds"] = perf_counter() - started
                        if event.get("type") == "tool_calls":
                            proposals += len(event.get("tool_calls") or [])
                        if event.get("type") == "finish":
                            finish = event.get("finish_reason")
                            finish_event, finishes = event, finishes + 1
                        else:
                            yield event
            if finish not in ("stop", "tool_calls") or finishes != 1:
                raise BenchmarkStopped("invalid_or_missing_finish")
            if self.live:
                usage = summarize_usage_capture()
                if not usage or usage["calls"] != 1 or usage.get("failed_calls") or any(
                    item.get("token_source") != "api" for item in usage["items"]
                ):
                    raise BenchmarkStopped("missing_single_api_usage")
            # Count all proposals, including denied/cached ones, after capturing
            # provider usage but before Pi can dispatch the completed response.
            self.tool_budget.reserve_proposals(proposals)
            # Some consumers stop at finish; validate usage before releasing it.
            yield finish_event
        except BaseException as exc:
            row["error_type"] = type(exc).__name__
            if isinstance(exc, (BenchmarkStopped, asyncio.CancelledError, GeneratorExit, KeyboardInterrupt)):
                raise
            raise BenchmarkStopped("provider_" + type(exc).__name__) from None
        finally:
            usage = summarize_usage_capture()
            if self.live and usage and usage["calls"] == 1 and all(item.get("token_source") == "api" for item in usage["items"]):
                row.update(token_source="api", input_tokens=usage["prompt_tokens"], output_tokens=usage["completion_tokens"],
                           cached_tokens=[item.get("cached_tokens") for item in usage["items"]], actual_models=usage["models"])
            row["wall_seconds"] = perf_counter() - started
            end_usage_capture(capture)


class ScriptedProvider:
    """Deterministic pipeline smoke test; never supplies fake API token usage."""
    def __init__(self, scenario):
        self.scenario = scenario

    async def chat_stream(self, **kwargs):
        if kwargs.get("tools") and not any(message.get("role") == "tool" for message in kwargs["messages"]):
            yield {"type": "tool_calls", "tool_calls": [{"id": "synthetic-model-read", "type": "function", "function": {
                "name": "health_query_batch", "arguments": json.dumps({"queries": [
                    {"dimension": "diet", "days": self.scenario.days}, {"dimension": "sleep", "days": self.scenario.days}]})}}]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            answer = ("本轮查询失败，无法确认睡眠和饮食记录，请稍后重试。" if self.scenario.state == "read_failure" else
                      "睡眠和饮食均未查到本轮范围内的记录，缺少数据，无法判断健康状态。" if self.scenario.state == "empty" else
                      "仅依据已返回样本作有限观察，不能据此判断完整健康状态。" if self.scenario.dense_records or self.scenario.days == 1 else
                      "睡眠记录显示420分钟、评分80；饮食有一条合成番茄记录，200千卡。未记录的指标仍未知，不能据此判断完整健康状态。")
            yield {"type": "content", "text": answer}
            yield {"type": "finish", "finish_reason": "stop"}


def tool_contract(request, result, scenario):
    queries = request.arguments.get("queries") if request.tool_name == "health_query_batch" else [request.arguments]
    start = (REFERENCE_NOW.date() - timedelta(days=scenario.days - 1)).isoformat()
    end = REFERENCE_NOW.date().isoformat()
    arguments_ok = bool(queries) and all(query.get("dimension") in {"sleep", "diet"}
        and query.get("days") == scenario.days and query.get("start_date") == start and query.get("end_date") == end
        for query in queries)
    if str(result).startswith("Error:"):
        return {"tool": request.tool_name, "arguments_ok": arguments_ok, "failed": True, "dimensions": sorted(query["dimension"] for query in queries), "records_ok": scenario.state == "read_failure"}
    payload = json.loads(result)
    items = payload.get("results", [payload])
    expected = {"sleep": [] if scenario.state == "empty" else [(end, 80, 420)],
                "diet": [] if scenario.state == "empty" or scenario.days == 1 else [((REFERENCE_NOW.date() - timedelta(days=1)).isoformat(), "合成番茄", 200)]}
    if scenario.dense_records and scenario.state != "empty":
        dates = [(REFERENCE_NOW.date() - timedelta(days=offset)).isoformat()
                 for offset in reversed(range(scenario.days))]
        expected = {"sleep": [(day, 80, 420) for day in dates],
                    "diet": [(day, "合成番茄", 200) for day in dates] + [(end, "合成番茄", None)]}
    valid, dimensions = True, []
    for item in items:
        dimension = item.get("dimension")
        dimensions.append(dimension)
        records = item.get("records", [])
        fields = ("record_date", "sleep_score", "total_sleep_duration") if dimension == "sleep" else ("record_date", "food_name", "calories")
        valid &= dimension in expected and [tuple(record.get(key) for key in fields) for record in records] == expected.get(dimension)
        if not records:
            valid &= item.get("availability") == "no_data"
    return {"tool": request.tool_name, "arguments_ok": arguments_ok, "failed": False,
            "dimensions": sorted(dimensions), "records_ok": bool(valid)}


async def run_sample(db, user_id, scenario, variant, model, budget, *, live, provider_factory=None, production_routing=False):
    if production_routing and not live:
        raise ValueError("production_routing_requires_live_opt_in")
    require_ephemeral(db)
    if variant not in VARIANTS or scenario.state not in {"available", "empty", "read_failure"} or scenario.days not in {1, 7, 31}:
        raise ValueError("unsupported_sample")
    from sqlalchemy import event as sqlalchemy_event
    from sqlalchemy.orm import sessionmaker
    from app.config import settings
    from app.models.agent_conversation import AgentMessage
    from app.services import agent_executor as ae, ai_consent
    from app.services.agent_kernel.types import ExecutionContext
    from app.services.llm import factory
    from app.services.llm.providers import openai_provider
    from app.services.health_context_lite_service import invalidate_health_context
    from eval.experimental_owned_read_preplan import install_owned_read_preplan
    from eval.experimental_read_synthesis import build_read_synthesis_parts

    row = {"case": scenario.id, "variant": variant, "model": model, "status": "running", "calls": [], "tool_contracts": [],
           "tool_attempts": 0, "database": "disposable_sqlite", "first_ui_content_seconds": None, "live": live,
           "wall_seconds": None, "database_errors": [], "rejected_tools": [], "knowledge_contracts": [],
           "query": scenario.query, "allow_knowledge": scenario.allow_knowledge, "gateway_decisions": [],
           "production_routing": production_routing, "decision_calls": []}
    original_factory = factory.create_provider_for_model_id
    make_provider = provider_factory or ((lambda: original_factory(model)) if live else (lambda: ScriptedProvider(scenario)))
    provider = MeasuredProvider(make_provider, model, budget, row["calls"], live=live)
    before = health_digest(db)
    started, task_started = perf_counter(), None
    invalidate_health_context(user_id)
    try:
        with ExitStack() as stack:
            bind = db.get_bind()
            engine = getattr(bind, "engine", bind)
            def database_error(context):
                row["database_errors"].append(type(context.original_exception).__name__)
            sqlalchemy_event.listen(engine, "handle_error", database_error)
            stack.callback(sqlalchemy_event.remove, engine, "handle_error", database_error)
            for name, value in (("domain_prompt_optimization", True), ("owned_read_preplanning", variant in {"runtime_preplan", "runtime_legacy_layout"}), ("agent_base_url", None), ("agent_api_key", None),
                                ("task_tiered_routing", True), ("llm_auto_recovery_enabled", False),
                                ("decision_mode", "on" if production_routing else "off"), ("staged_response_mode", "off"),
                                ("decision_provider", "laya"), ("decision_admin_control_enabled", False)):
                stack.enter_context(patch.object(settings, name, value))
            stack.enter_context(patch.object(openai_provider, "_DEFAULT_MAX_RETRIES", 0))
            client_kwargs = openai_provider.OpenAIProvider._client_kwargs
            # Defaults are absent from the production cache key. Include the
            # retry limit explicitly so a pre-existing retrying pool cannot win.
            stack.enter_context(patch.object(openai_provider.OpenAIProvider, "_client_kwargs",
                                            lambda self: {**client_kwargs(self), "max_retries": 0}))
            stack.enter_context(patch.object(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind())))
            # Twin workers must see the same synthetic subject as the request.
            stack.enter_context(patch("app.database.SessionLocal", sessionmaker(bind=db.get_bind())))
            # Keep real provider consent checks, with an audited synthetic subject.
            ai_consent.update_ai_consent(db, user_id, True, ai_consent.POLICY_VERSION)
            stack.enter_context(ai_consent.ai_user_scope(user_id))
            stack.enter_context(patch("app.utils.redis_cache.get_redis_client", lambda: None))
            stack.enter_context(patch("app.twin.cache.get_cached_twin", lambda *a, **k: None))
            stack.enter_context(patch("app.twin.cache.set_cached_twin", lambda *a, **k: False))
            stack.enter_context(patch("app.twin.cache.invalidate_twin", lambda *a, **k: None))
            # The profile is background, but its clock must still agree with
            # the frozen request clock. Never send contradictory synthetic times.
            assert REFERENCE_NOW.hour == 23
            stack.enter_context(patch("app.services.health_context_lite_service._get_time_period",
                                      lambda: (REFERENCE_NOW.strftime("%H:%M"), "深夜")))
            clock = ExecutionContext.now.__func__
            stack.enter_context(patch.object(ExecutionContext, "now", classmethod(lambda cls, **kwargs: clock(cls, **{**kwargs, "now_utc": REFERENCE_NOW}))))
            for name in ("create_provider_for_model_id", "create_provider_for_user", "get_llm_provider"):
                original = getattr(factory, name)
                def measured_factory(*args, _original=original, **kwargs):
                    actual = _original(*args, **kwargs)
                    if isinstance(actual, MeasuredProvider):
                        return actual
                    return MeasuredProvider(lambda: actual, getattr(actual, "model", model), budget,
                        row["calls"], live=live, tool_budget=provider.tool_budget, preserve_controls=True)
                stack.enter_context(patch.object(factory, name,
                    measured_factory if production_routing else lambda *a, **k: provider))
            if production_routing:
                from app.services.decisions import routing as decision_routing
                original_decision_factory = decision_routing.provider_from_settings
                class BoundedDecision:
                    async def evaluate(self, request, *, user_id):
                        if row["decision_calls"]:
                            raise BenchmarkStopped("decision_call_budget")
                        budget.reserve()
                        entry = {"token_source": "unknown" if live else "synthetic",
                                 "input_tokens": None, "output_tokens": None, "status": "running"}
                        row["decision_calls"].append(entry)
                        start = perf_counter()
                        try:
                            result = await original_decision_factory().evaluate(request, user_id=user_id)
                            entry.update(status="passed", model=result.model,
                                input_tokens=result.input_tokens if live else None,
                                output_tokens=result.output_tokens if live else None,
                                token_source="api" if live else "synthetic")
                            return result
                        except BaseException as exc:
                            entry.update(status="failed", error_type=type(exc).__name__)
                            raise
                        finally:
                            entry["wall_seconds"] = perf_counter() - start
                stack.enter_context(patch.object(decision_routing, "provider_from_settings", BoundedDecision))
            if not production_routing:
                stack.enter_context(patch("app.services.llm.task_routing.pick_model_id_by_tier", lambda *a, **k: model))
            if variant in {"p1", "combined"}:
                stack.enter_context(patch("app.services.agent_prompt_sections.build_base_prompt_parts", build_read_synthesis_parts))
            if scenario.state == "read_failure":
                def failed_read(*args, **kwargs):
                    raise RuntimeError("synthetic_read_unavailable")
                stack.enter_context(patch("app.services.agent_longitudinal_read.read_longitudinal_health_query", failed_read))
            executor = ae.AgentExecutor(db)
            if variant not in {"runtime_preplan", "runtime_legacy_layout"}:
                # Freeze the old runtime's model-first baseline. Historical
                # eval variants remain independent; never stack preplanners.
                stack.enter_context(patch.object(executor, "_preplanned_owned_read_calls", lambda *a, **k: []))
            if variant == "runtime_legacy_layout":
                from app.services import agent_composed_read_completion as completion_module
                original_instructions = completion_module.read_scope_synthesis_instructions
                stack.enter_context(patch.object(completion_module, "read_scope_synthesis_instructions",
                    lambda scope, **kwargs: original_instructions(scope, include_layout=True)))
            if not production_routing:
                stack.enter_context(patch.object(executor, "_resolve_chat_provider", lambda tools: (provider, tools)))
            dispatch = executor._dispatch_tool_request
            from app.services.agent_kernel.tool_gateway import ToolGateway
            preflight = ToolGateway.preflight
            def measured_preflight(gateway, request):
                decision = preflight(gateway, request)
                # Synthetic-only inputs; retain narrow calendar/dimension
                # diagnostics rather than arbitrary model argument payloads.
                raw_queries = request.arguments.get("queries", [request.arguments])
                projected = []
                if isinstance(raw_queries, list):
                    projected = [{key: query[key] for key in (
                        "dimension", "days", "start_date", "end_date", "timezone") if key in query}
                        for query in raw_queries if isinstance(query, dict)]
                row["gateway_decisions"].append({
                    "tool": request.tool_name, "action": decision.action,
                    "reason": decision.reason, "requested_read_scope": projected,
                })
                return decision
            stack.enter_context(patch.object(ToolGateway, "preflight", measured_preflight))
            async def measured_dispatch(request, token):
                allowed = {"health_query", "health_query_batch"}
                if scenario.allow_knowledge:
                    allowed.add("knowledge_search")
                if request.tool_name not in allowed:
                    row["rejected_tools"].append({"name": request.tool_name, "reason": "out_of_scope"})
                    raise BenchmarkStopped("unexpected_tool_or_tool_budget")
                try:
                    provider.tool_budget.reserve_dispatch()
                except BenchmarkStopped:
                    row["rejected_tools"].append({"name": request.tool_name, "reason": "budget"})
                    raise
                row["tool_attempts"] += 1
                if request.tool_name == "knowledge_search":
                    # Actual Gateway and local reviewed-KB retrieval. The
                    # disposable fixture has no approved sources, so only an
                    # honest miss is valid; retrieval errors are not misses.
                    result = await dispatch(request, token)
                    row["knowledge_contracts"].append({
                        "tool": request.tool_name,
                        "honest_empty_kb": "已审定知识库未命中" in str(result)
                            and "请如实说明缺少本系统已审定依据" in str(result),
                        "result": str(result),
                    })
                    return result
                queries = request.arguments.get("queries") if request.tool_name == "health_query_batch" else [request.arguments]
                if (not isinstance(queries, list) or not 1 <= len(queries) <= 2
                    or any(not isinstance(query, dict) or query.get("dimension") not in {"sleep", "diet"} for query in queries)
                    or len({query["dimension"] for query in queries}) != len(queries)):
                    raise BenchmarkStopped("unexpected_read_scope")
                result = await dispatch(request, token)
                row["tool_contracts"].append(tool_contract(request, result, scenario))
                return result
            stack.enter_context(patch.object(executor, "_dispatch_tool_request", measured_dispatch))
            if variant in {"p2", "combined"}:
                install_owned_read_preplan(executor)
            elif variant == "empty_terminal":
                from eval.experimental_empty_read_terminal import install_empty_read_terminal
                install_empty_read_terminal(executor)
            elif variant == "evidence_compact":
                from eval.experimental_read_evidence_format import install_read_evidence_format
                install_read_evidence_format(executor)
            done, chunks = None, []
            task_started = perf_counter()
            try:
                async with asyncio.timeout(90):
                    async with aclosing(executor.run_stream(user_id, scenario.query, channel="typed", client_turn_id=uuid4().hex,
                        extra_context=json.dumps({"model_id": model}))) as events:
                        async for event in events:
                            if event.get("event") == "tool_call":
                                # Includes Pi replays and server preplans, never
                                # counts a retry heartbeat as a new request.
                                provider.tool_budget.begin_execution()
                            if event.get("event") == "token":
                                text = event.get("data", {}).get("content", "")
                                chunks.append(text)
                                if text.strip() and row["first_ui_content_seconds"] is None:
                                    row["first_ui_content_seconds"] = perf_counter() - task_started
                            elif event.get("event") == "done":
                                done = event["data"]
            finally:
                row["wall_seconds"] = perf_counter() - task_started
                row["tool_budget"] = dict(vars(provider.tool_budget))
                if production_routing:
                    route = executor._decision_route
                    row["decision_routing"] = route.metadata() if route is not None else None
                    row["effective_model_id"] = executor._last_effective_model_id
                row["logical_tool_source"] = "model_and_server_preplan" if variant in {"p2", "combined", "runtime_preplan", "runtime_legacy_layout"} else "model_and_existing_server_fallback"
            if done is None:
                raise BenchmarkStopped("missing_done")
            saved = db.get(AgentMessage, done.get("message_id"))
            contracts = row["tool_contracts"]
            dimensions = {dimension for contract in contracts for dimension in contract["dimensions"]}
            outcome = done.get("turn_outcome", {}).get("status")
            quality = {"stream_matches_saved": saved is not None and saved.content == "".join(chunks),
                       "database_context_intact": not row["database_errors"],
                       "health_rows_unchanged": before == health_digest(db), "no_write_receipt": not done.get("write_receipts"),
                       "read_contracts": bool(contracts) and all(c["arguments_ok"] and c["records_ok"] for c in contracts) and dimensions == {"sleep", "diet"},
                       "knowledge_contracts": all(c["honest_empty_kb"] for c in row["knowledge_contracts"]),
                       "expected_outcome": outcome == ("failed" if scenario.state == "read_failure" else "complete"),
                       "answer_present": bool(saved and saved.content.strip()), "semantic_review": "required"}
            if production_routing:
                route = row.get("decision_routing") or {}
                quality["decision_route_exercised"] = (route.get("mode") == "on"
                    and route.get("status") in {"accepted", "partial", "abstained"}
                    and len(row["decision_calls"]) == 1 and row["decision_calls"][0]["status"] == "passed")
            row.update(quality=quality, agent_kernel=done.get("perf", {}).get("agent_kernel"), answer=saved.content if saved else None,
                       outcome=outcome, completion_status=done.get("completion_status"),
                       runtime_preplanned=done.get("perf", {}).get("owned_read_preplanned", False),
                       runtime_model_call_count=done.get("perf", {}).get("model_call_count"))
            row["status"] = "passed_contracts" if all(value for key, value in quality.items() if key != "semantic_review") and row["agent_kernel"] == "pi" else "failed_contracts"
    except BaseException as exc:
        row.update(status="cancelled" if isinstance(exc, asyncio.CancelledError) else "failed", error_type=type(exc).__name__)
        if isinstance(exc, BenchmarkStopped):
            row["stop_reason"] = str(exc)
        if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)):
            # The batch caller receives this sample even when cancellation propagates.
            exc.benchmark_sample = row
            raise
    finally:
        row["evaluation_seconds"] = perf_counter() - started
        invalidate_health_context(user_id)
    return row
