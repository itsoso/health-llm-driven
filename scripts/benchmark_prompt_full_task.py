#!/usr/bin/env python3
"""Whole synthetic read-task A/B, default plan only; explicit live API opt-in.

Use --scripted for real Pi/Gateway/persistence with a scripted provider. Live
mode retains real audited consent and requires APP_ENV=test, memory SQLite.
Never use production data. Passing this small screen is not noninferiority.
"""
import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from eval.full_task_prompt_benchmark import CallBudget, SCENARIOS, run_sample, seed_synthetic_records, require_ephemeral


def summary(rows):
    groups = {}
    for row in rows:
        groups.setdefault((row["model"], row["variant"]), []).append(row)
    result = []
    for (model, variant), samples in sorted(groups.items()):
        calls = [call for sample in samples for call in sample["calls"]]
        known = [call for call in calls if call["token_source"] == "api"]
        times = sorted(sample["wall_seconds"] for sample in samples if sample.get("wall_seconds") is not None)
        result.append({"model": model, "variant": variant, "tasks": len(samples), "provider_attempts": len(calls),
                       "passed_contracts": sum(sample["status"] == "passed_contracts" for sample in samples),
                       "failed_tasks": sum(sample["status"] != "passed_contracts" for sample in samples),
                       "api_input_tokens_known": sum(call["input_tokens"] for call in known),
                       "api_output_tokens_known": sum(call["output_tokens"] for call in known),
                       "usage_unknown_calls": len(calls) - len(known),
                       "all_api_usage_known": bool(calls) and len(known) == len(calls),
                       "timed_tasks": len(times),
                       "wall_seconds_all_tasks": {f"p{p}": times[math.ceil(len(times) * p / 100) - 1] if times else None for p in (50, 95, 99)}})
    return result


async def run(args):
    cases = [case for case in SCENARIOS if case.id in args.case] if args.case else [
        case for case in SCENARIOS if case.id.startswith("owned_read_")]
    models = args.model or ["qwen3.8-flash", "qwen3.8-max"]
    if getattr(args, "baseline_only", False) and args.variant:
        raise ValueError("baseline_only_conflicts_with_variant")
    variants = ["baseline"] if getattr(args, "baseline_only", False) else ["baseline", *(args.variant or ["p1", "p2", "combined"])]
    tasks = len(cases) * len(models) * len(variants) * args.repetitions
    if not 1 <= args.repetitions <= 3 or not 1 <= args.max_api_calls <= 256 or len(set(models)) != len(models) or len(set(variants)) != len(variants):
        raise ValueError("invalid_or_duplicate_batch_parameters")
    if (args.scripted or args.include_live_llm) and tasks * 3 > args.max_api_calls:
        raise ValueError("worst_case_calls_exceed_budget")
    report = {"status": "running" if args.scripted or args.include_live_llm else "plan_only", "batch_id": uuid4().hex,
              "mode": "live" if args.include_live_llm else "scripted" if args.scripted else "plan",
              "models": models, "variants": variants, "cases": [case.id for case in cases],
              "planned_tasks": tasks, "max_provider_attempts": args.max_api_calls, "per_task_call_cap": 3,
              "per_task_tool_cap": 3, "max_input_bytes_per_call": 262144, "requested_max_output_tokens_per_call": 1200,
              "provider_timeout_seconds": 45, "task_timeout_seconds": 90,
              "candidate_disposition": "eval_only", "semantic_noninferiority": "not_established", "rows": [],
              "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in (
                  "backend/eval/full_task_prompt_benchmark.py", "scripts/benchmark_prompt_full_task.py",
                  "backend/eval/experimental_read_synthesis.py", "backend/eval/experimental_owned_read_preplan.py",
                  "backend/app/services/agent_executor.py", "backend/app/services/agent_prompt_sections.py",
                  "backend/app/services/agent_tool_prompt_projection.py", "backend/app/services/tool_schema_registry.py",
                  "backend/app/services/llm/providers/openai_provider.py", "backend/app/services/llm/usage_tracker.py")},
              "limits": ["Fixed synthetic read-task screen, not production load or full holdout coverage.",
                         "Fixed requested model, temperature zero and output cap; decision/staged routing off and not under test.",
                         "Redis/Twin cache disabled; application prompts and read adapters retained.",
                         "Unseeded clinical/CGM context is empty; optional local knowledge base is absent. Not rich-patient coverage.",
                         "Per-sample synthetic user with real audited consent; no production database.",
                         "First UI content is not a clinically useful-result metric.",
                         "Small-sample percentiles and deterministic contracts do not prove noninferiority.",
                         "The output cap is a request parameter; reported API completion usage can exceed it and remains recorded.",
                         "No real API token/latency claims in scripted mode; no automatic runtime enablement."]}
    def save():
        report["summary"] = summary(report["rows"])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    save()
    if not args.scripted and not args.include_live_llm:
        return 0
    try:
        from app.config import settings
        from sqlalchemy.engine import make_url
        url = make_url(settings.effective_database_url)
        if settings.app_env != "test" or url.get_backend_name() != "sqlite" or url.database not in (None, "", ":memory:"):
            raise RuntimeError("full_task_eval_requires_test_in_memory_database")
        # SQLite compatibility is eval-process-local, identical to project unit fixtures.
        from sqlalchemy.ext.compiler import compiles
        from sqlalchemy.dialects.postgresql import JSONB
        @compiles(JSONB, "sqlite")
        def compile_jsonb(type_, compiler, **kwargs):
            return "JSON"
        import app.models
        # These context collectors import their models lazily; app.models alone
        # does not register their tables before the first synthetic task.
        import app.models.cgm_reading
        import app.models.family_health
        import app.models.clinical_journal
        from app.database import Base, engine, SessionLocal
        from app.models.user import User
        with SessionLocal() as db:
            require_ephemeral(db)
        Base.metadata.create_all(engine)
        budget = CallBudget(args.max_api_calls)
        for index, case in enumerate(cases):
            for model in models:
                for repeat in range(args.repetitions):
                    order = variants if (index + repeat) % 2 == 0 else list(reversed(variants))
                    for variant in order:
                        with SessionLocal() as db:
                            user = User(name="Synthetic evaluation subject", email=f"eval-{uuid4().hex}@example.invalid", is_active=True, is_approved=True)
                            db.add(user)
                            db.commit()
                            seed_synthetic_records(db, user.id, case)
                            try:
                                row = await run_sample(db, user.id, case, variant, model, budget, live=args.include_live_llm)
                            except (asyncio.CancelledError, KeyboardInterrupt) as exc:
                                if hasattr(exc, "benchmark_sample"):
                                    report["rows"].append(exc.benchmark_sample)
                                raise
                        row["repeat"] = repeat
                        report["rows"].append(row)
                        save()
                        if row["status"] != "passed_contracts":
                            report["status"] = "failed"
                            save()
                            return 1
        report["status"] = "passed_contracts_only" if args.include_live_llm else "scripted_contracts_passed"
        save()
        return 0
    except BaseException as exc:
        report.update(status="cancelled" if isinstance(exc, asyncio.CancelledError) else "failed", error_type=type(exc).__name__)
        save()
        if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)):
            raise
        return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--scripted", action="store_true")
    modes.add_argument("--include-live-llm", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", choices=["qwen3.8-flash", "qwen3.8-max"], action="append")
    parser.add_argument("--variant", choices=["p1", "p2", "combined"], action="append")
    parser.add_argument("--baseline-only", action="store_true", help="Evaluate the runtime in this checkout without injecting an experimental variant.")
    parser.add_argument("--case", choices=[case.id for case in SCENARIOS], action="append")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--max-api-calls", type=int, default=72)
    args = parser.parse_args()
    try:
        return asyncio.run(run(args))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
