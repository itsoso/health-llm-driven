#!/usr/bin/env python3
"""Two bounded pytest processes, each owning a freshly created local test database.

Selectors preserve the original PostgreSQL CI suite and include personal/Health
navigation transaction and concurrency coverage. Original file grouping uses
run 37877803968 completion timings (approximately 168s/167s, excluding startup).
Migration/idempotency and real Redis checks remain preceding workflow steps.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from urllib.parse import urlsplit, urlunsplit

import psycopg2
from psycopg2 import sql

SHARDS = (
    (
        "tests/test_agent_runtime_tool_operations.py",  # 78s
        "tests/test_remote_health_transport.py",  # 33s
        "tests/test_agent_runtime_reconciliation.py",  # 27s
        "tests/test_agent_supplement_persistence_postgres.py",  # 17s
        "tests/test_pi_kernel_executor.py",  # 10s
        "tests/test_latest_meal_correction.py",  # 4s
        "tests/test_life_navigation.py",
        "tests/test_health_navigation_concurrency.py",
    ),
    (
        "tests/test_agent_runtime_concurrency.py",
        "tests/test_supplement_taken_count_drop_migration.py",
        "tests/test_diet_spoken_fraction_correction.py",
        "tests/test_pi_kernel_write_reconciliation.py",
        "tests/test_medication_intake_batch.py",
        "tests/test_write_intent_medication_batch_schema.py",
        "tests/test_medication_intake_batch_postgres.py",
        "tests/test_user_merge_security.py::test_postgres_concurrent_same_source_merge_has_one_winner_and_no_data_loss",
        "tests/test_registration_invitation_migration_postgres.py::test_postgres_managed_migration_is_replay_safe_and_enforces_contract",
        "tests/test_invited_phone_registration_postgres.py",
        "tests/test_registration_invitation_service.py::test_postgres_concurrent_grant_consumption_has_exactly_one_winner",
        "tests/test_app_store_demo_account.py::test_demo_seed_removes_dependent_rows_before_parent_records",
        "tests/test_remote_health_oauth.py",
        "tests/test_remote_health_queries.py",
        "tests/test_health_week_navigation.py",
        "tests/test_lifenav_grants.py",
    ),
)
OWN_NAME = re.compile(r"reva_ci_test_[0-9a-f]{32}_0[12]\Z")


def validate_environment(env):
    if any(env.get(key) for key in ("PGSERVICE", "PGSERVICEFILE", "PGSYSCONFDIR")):
        raise ValueError("PostgreSQL service indirection is forbidden")
    if env.get("APP_ENV") != "test" or env.get("CI") != "true":
        raise ValueError("PostgreSQL CI requires APP_ENV=test and CI=true")
    validate_redis_url(env)
    raw = env.get("TEST_DATABASE_URL", "")
    if raw != env.get("DATABASE_URL"):
        raise ValueError("PostgreSQL CI database URLs must match")
    url = urlsplit(raw)
    if (url.scheme != "postgresql" or url.hostname not in {"localhost", "127.0.0.1"}
            or url.path != "/health_runtime_test" or url.query or url.fragment
            or not url.username or not url.port):
        raise ValueError("PostgreSQL CI requires an explicit local health_runtime_test database")
    return url


def validate_redis_url(env):
    url = urlsplit(env.get("REDIS_URL", ""))
    if (url.scheme != "redis" or url.hostname not in {"localhost", "127.0.0.1"}
            or not url.port or url.path != "/0" or url.query or url.fragment):
        raise ValueError("PostgreSQL CI requires explicit local Redis base database 0")
    return url


def verify_redis_ready(env):
    import redis
    url = validate_redis_url(env)
    for database in (13, 14):
        with redis.Redis.from_url(urlunsplit(url._replace(path=f"/{database}")),
                socket_connect_timeout=2, socket_timeout=2) as client:
            if not client.ping() or client.dbsize() != 0:
                raise RuntimeError("isolated Redis shard databases must be reachable and empty")


def worker_environment(env, database):
    url = validate_environment(env)
    if not OWN_NAME.fullmatch(database):
        raise ValueError("invalid owned test database name")
    child = dict(env)
    # No accidental service/options redirection or unrelated pytest selection.
    for key in tuple(child):
        if key.startswith("PG") or key in {"PYTEST_ADDOPTS", "TEST_LIVE_RUN_BROKER_URL"}:
            del child[key]
    child["DATABASE_URL"] = child["TEST_DATABASE_URL"] = urlunsplit(url._replace(path="/" + database))
    child["REDIS_URL"] = urlunsplit(validate_redis_url(env)._replace(path=f"/{12 + int(database[-1])}"))
    child["PYTHONUNBUFFERED"] = "1"
    return child


def safe_status(status):
    return json.dumps(status, sort_keys=True)


def connect_admin(env):
    from urllib.parse import unquote
    url = validate_environment(env)
    # Explicit libpq parameters prevent PGSERVICE / PGOPTIONS redirection.
    connection = psycopg2.connect(host="127.0.0.1", hostaddr="127.0.0.1", port=url.port,
        dbname="health_runtime_test", user=unquote(url.username), password=unquote(url.password or ""),
        options="-c statement_timeout=30000 -c lock_timeout=10000", sslmode="disable", connect_timeout=10)
    connection.autocommit = True
    return connection


def run(env, output, *, groups=SHARDS, connect=connect_admin, popen=subprocess.Popen, redis_check=verify_redis_ready):
    validate_environment(env)
    if len(groups) != 2 or any(not group for group in groups):
        raise ValueError("exactly two nonempty PostgreSQL shards required")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "selection.json").write_text(safe_status({"shards": groups}) + "\n")
    started = time.monotonic()
    status = {"state": "running", "exit_codes": [], "databases": [], "elapsed_seconds": None}
    created, processes, logs = [], [], []
    connection = None
    try:
        redis_check(env)
        connection = connect(env)
        run_id = uuid.uuid4().hex
        with connection.cursor() as cursor:
            for index in (1, 2):
                name = f"reva_ci_test_{run_id}_{index:02d}"
                # No IF NOT EXISTS: a collision must fail; only successful creates are owned.
                cursor.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
                created.append(name)
                status["databases"] = list(created)
        for index, (name, selectors) in enumerate(zip(created, groups), 1):
            log = (output / f"shard-{index}.log").open("xb")
            logs.append(log)
            command = [sys.executable, "-m", "pytest", "-q", "--no-cov", "--tb=short", "--maxfail=5",
                "--timeout=120", "--timeout-method=signal", "--durations=0",
                "-o", f"cache_dir={output / f'cache-{index}'}",
                f"--junitxml={output / f'shard-{index}.xml'}", *selectors]
            processes.append(popen(command, cwd=Path(__file__).resolve().parents[1] / "backend",
                env=worker_environment(env, name), stdout=log, stderr=subprocess.STDOUT))
            print(f"Launched PostgreSQL shard {index}; log: {output / f'shard-{index}.log'}", flush=True)
        deadline = time.monotonic() + 1000
        for process in processes:
            status["exit_codes"].append(process.wait(timeout=max(1, deadline - time.monotonic())))
        status["state"] = "passed" if status["exit_codes"] == [0, 0] else "failed"
    except BaseException as exc:
        status["state"] = "failed"
        status["error_type"] = type(exc).__name__  # Never print credentials/connection errors.
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        for process in processes:
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
            except Exception as exc:
                status["state"] = "failed"
                status.setdefault("termination_errors", []).append(type(exc).__name__)
        for log in logs:
            log.close()
        if connection is not None:
            for name in reversed(created):
                try:
                    with connection.cursor() as cursor:
                        # No FORCE and never touch the base database or pre-existing databases.
                        cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
                except Exception as exc:
                    status["state"] = "failed"
                    status.setdefault("cleanup_errors", []).append(type(exc).__name__)
            connection.close()
        status["elapsed_seconds"] = round(time.monotonic() - started, 3)
        (output / "summary.json").write_text(safe_status(status) + "\n")
        print(safe_status(status), flush=True)
        for index in range(1, len(logs) + 1):
            print(f"PostgreSQL shard {index}: {output / f'shard-{index}.log'}", flush=True)
            print((output / f"shard-{index}.log").read_text(errors="replace"), flush=True)
    return 0 if status["state"] == "passed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        return run(os.environ, args.output)
    except Exception as exc:
        print(f"PostgreSQL CI refused: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
