"""Fail-closed orchestration and unchanged PostgreSQL test selection."""
import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("run_postgres_ci", ROOT / "scripts/run_postgres_ci.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

# Exact selectors from the pre-parallel CI command (313 items on 2c6ee449d).
LEGACY_SELECTORS = '''test_agent_runtime_concurrency.py
test_agent_runtime_tool_operations.py
test_agent_runtime_reconciliation.py
test_agent_supplement_persistence_postgres.py
test_supplement_taken_count_drop_migration.py
test_latest_meal_correction.py
test_diet_spoken_fraction_correction.py
test_pi_kernel_executor.py
test_pi_kernel_write_reconciliation.py
test_medication_intake_batch.py
test_write_intent_medication_batch_schema.py
test_medication_intake_batch_postgres.py
test_user_merge_security.py::test_postgres_concurrent_same_source_merge_has_one_winner_and_no_data_loss
test_registration_invitation_migration_postgres.py::test_postgres_managed_migration_is_replay_safe_and_enforces_contract
test_invited_phone_registration_postgres.py
test_registration_invitation_service.py::test_postgres_concurrent_grant_consumption_has_exactly_one_winner
test_app_store_demo_account.py::test_demo_seed_removes_dependent_rows_before_parent_records
test_remote_health_oauth.py
test_remote_health_queries.py
test_remote_health_transport.py'''.splitlines()


def test_catalog_preserves_exact_original_selectors_once():
    selectors = [s for group in runner.SHARDS for s in group]
    assert len(runner.SHARDS) == 2
    assert len(selectors) == len(set(selectors))
    assert set(selectors) == {"tests/" + s for s in LEGACY_SELECTORS} | {"tests/test_life_navigation.py", "tests/test_health_week_navigation.py", "tests/test_health_navigation_concurrency.py", "tests/test_lifenav_grants.py"}


def config():
    return {"APP_ENV": "test", "CI": "true", "REDIS_URL": "redis://127.0.0.1:6379/0", "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/health_runtime_test", "TEST_DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/health_runtime_test"}


@pytest.mark.parametrize("key,value", [("APP_ENV", "production"), ("CI", "false"), ("TEST_DATABASE_URL", ""), ("DATABASE_URL", "postgresql://localhost/production")])
def test_rejects_unsafe_or_mismatched_environment(key, value):
    env = config(); env[key] = value
    with pytest.raises(ValueError): runner.validate_environment(env)


@pytest.mark.parametrize("url", ["postgresql://example.com/health_runtime_test", "postgresql://localhost/production", "postgresql://localhost/health_runtime_test?host=evil", "sqlite:///:memory:", "postgresql://localhost/health_runtime_test#x"])
def test_rejects_nonlocal_or_unexpected_database(url):
    env = config(); env.update(DATABASE_URL=url, TEST_DATABASE_URL=url)
    with pytest.raises(ValueError): runner.validate_environment(env)


def test_worker_binds_both_urls_and_isolates_live_redis():
    env = runner.worker_environment(config(), "reva_ci_test_" + "a" * 32 + "_01")
    assert env["DATABASE_URL"] == env["TEST_DATABASE_URL"]
    assert env["TEST_DATABASE_URL"].endswith("/reva_ci_test_" + "a" * 32 + "_01")
    assert env["REDIS_URL"] == "redis://127.0.0.1:6379/13"
    assert "postgres:postgres" not in runner.safe_status({"exit_codes": [0, 1]})


@pytest.mark.parametrize("name", ["health_runtime_test", "reva_ci_test_x", "production", 'reva_ci_test_"; DROP DATABASE postgres;'])
def test_worker_rejects_non_owned_database_names(name):
    with pytest.raises(ValueError): runner.worker_environment(config(), name)

class Cursor:
    def __init__(self, connection): self.connection = connection
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, query):
        value = repr(query)
        self.connection.queries.append(value)
        if "CREATE DATABASE" in value:
            self.connection.creates += 1
            if self.connection.creates == self.connection.fail_create:
                raise RuntimeError("creation refused")
        if "DROP DATABASE" in value and self.connection.fail_drop:
            raise RuntimeError("database remains busy")


class Connection:
    def __init__(self, fail_create=None, fail_drop=False):
        self.fail_create, self.fail_drop = fail_create, fail_drop
        self.creates, self.queries, self.closed = 0, [], False
    def cursor(self): return Cursor(self)
    def close(self): self.closed = True


class Process:
    def __init__(self, code): self.code = code
    def wait(self, timeout): return self.code
    def poll(self): return self.code


@pytest.mark.parametrize("codes,expected", [([0, 0], 0), ([1, 0], 1), ([0, 5], 1), ([-9, 0], 1)])
def test_waits_for_both_children_and_propagates_each_failure(tmp_path, codes, expected):
    connection, calls = Connection(), []
    def spawn(command, **kwargs):
        calls.append((command, kwargs))
        return Process(codes[len(calls) - 1])
    assert runner.run(config(), tmp_path / "run", connect=lambda _: connection, redis_check=lambda _: None, popen=spawn) == expected
    assert len(calls) == 2
    urls = [kwargs["env"]["TEST_DATABASE_URL"] for _, kwargs in calls]
    assert urls[0] != urls[1]
    assert all(kwargs["env"]["DATABASE_URL"] == url for (_, kwargs), url in zip(calls, urls))
    assert len([q for q in connection.queries if "DROP DATABASE" in q]) == 2
    assert connection.closed
    for command, _ in calls:
        assert "--timeout=120" in command and "--durations=0" in command
    import json
    assert json.loads((tmp_path / "run/summary.json").read_text())["exit_codes"] == codes


@pytest.mark.parametrize('run_id', ['020afaf053a745c6a81a5dee7097df3a', '01' + 'a' * 30, 'a' * 32])
def test_creation_collision_never_drops_unowned_database(tmp_path, monkeypatch, run_id):
    monkeypatch.setattr(runner.uuid, 'uuid4', lambda: runner.uuid.UUID(hex=run_id))
    connection = Connection(fail_create=2)
    def must_not_spawn(*args, **kwargs): pytest.fail("must create both isolated databases first")
    assert runner.run(config(), tmp_path / "run", connect=lambda _: connection, redis_check=lambda _: None, popen=must_not_spawn) == 1
    drops = [q for q in connection.queries if "DROP DATABASE" in q]
    # Match the complete owned identifier: the random run ID can start with 02.
    expected = runner.sql.SQL("DROP DATABASE {}").format(
        runner.sql.Identifier(f"reva_ci_test_{run_id}_01"))
    assert drops == [repr(expected)]


def test_cleanup_failure_is_red_even_when_pytest_passes(tmp_path):
    connection = Connection(fail_drop=True)
    assert runner.run(config(), tmp_path / "run", connect=lambda _: connection, redis_check=lambda _: None, popen=lambda *a, **k: Process(0)) == 1


def test_spawn_failure_cleans_created_databases(tmp_path):
    connection = Connection()
    def fail(*args, **kwargs): raise OSError("cannot launch")
    assert runner.run(config(), tmp_path / "run", connect=lambda _: connection, redis_check=lambda _: None, popen=fail) == 1
    assert len([q for q in connection.queries if "DROP DATABASE" in q]) == 2


def test_connection_failure_does_not_retry_or_spawn(tmp_path):
    calls = []
    def fail(env): calls.append(1); raise OSError("refused")
    assert runner.run(config(), tmp_path / "run", connect=fail, redis_check=lambda _: None) == 1
    assert calls == [1]


@pytest.mark.parametrize("key", ["PGSERVICE", "PGSERVICEFILE", "PGSYSCONFDIR"])
def test_forbids_libpq_service_indirection(key):
    env = config(); env[key] = "production"
    with pytest.raises(ValueError): runner.validate_environment(env)

@pytest.mark.skipif(not (os.getenv("REVA_PG_PARALLEL_TEST_URL") and os.getenv("REVA_REDIS_PARALLEL_TEST_URL")), reason="requires dedicated local PostgreSQL test cluster")
def test_real_postgres_simultaneous_same_table_isolated_and_cleanup(tmp_path):
    import json
    env = config()
    env["REDIS_URL"] = os.environ["REVA_REDIS_PARALLEL_TEST_URL"]
    env.update(DATABASE_URL=os.environ["REVA_PG_PARALLEL_TEST_URL"], TEST_DATABASE_URL=os.environ["REVA_PG_PARALLEL_TEST_URL"])
    env.update({k: v for k, v in os.environ.items() if k in {"PATH", "HOME"}})
    probes = []
    for index in (1, 2):
        probe = tmp_path / f"test_probe_{index}.py"
        probe.write_text('''import json, os, time
from pathlib import Path
import psycopg2
import redis

def test_isolation():
    assert os.environ['DATABASE_URL'] == os.environ['TEST_DATABASE_URL']
    cache = redis.Redis.from_url(os.environ['REDIS_URL'])
    key = 'reva-isolation:' + DIRECTORY
    assert cache.ping()
    cache.set(key, INDEX, ex=60)
    with psycopg2.connect(os.environ['DATABASE_URL']) as connection:
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE same_table (value INTEGER)')
            cursor.execute('INSERT INTO same_table VALUES (%s)', (INDEX,))
            connection.commit()
            Path(DIRECTORY, f'ready-{INDEX}').write_text('ready')
            deadline = time.monotonic() + 30
            while not Path(DIRECTORY, f'ready-{3-INDEX}').exists():
                assert time.monotonic() < deadline, 'children did not overlap'
                time.sleep(0.05)
            assert cache.get(key) == str(INDEX).encode()
            assert cache.connection_pool.connection_kwargs['db'] == 12 + INDEX
            cache.delete(key)
            cache.close()
            cursor.execute('SELECT value FROM same_table')
            assert cursor.fetchall() == [(INDEX,)]
            cursor.execute('SELECT current_database()')
            Path(DIRECTORY, f'database-{INDEX}.json').write_text(json.dumps(cursor.fetchone()[0]))
            cursor.execute('DROP TABLE same_table')
'''.replace('INDEX', str(index)).replace('DIRECTORY', repr(str(tmp_path))))
        probes.append((str(probe),))
    assert runner.run(env, tmp_path / "real", groups=probes) == 0
    databases = [json.loads((tmp_path / f"database-{i}.json").read_text()) for i in (1, 2)]
    assert len(set(databases)) == 2 and all(runner.OWN_NAME.fullmatch(n) for n in databases)
    with runner.connect_admin(env) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT datname FROM pg_database WHERE datname = ANY(%s)', (databases,))
            assert cursor.fetchall() == []


@pytest.mark.skipif(not (os.getenv("REVA_PG_PARALLEL_TEST_URL") and os.getenv("REVA_REDIS_PARALLEL_TEST_URL")), reason="requires dedicated local PostgreSQL test cluster")
def test_real_postgres_collision_keeps_preexisting_database(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from psycopg2 import sql
    env = config(); env["REDIS_URL"] = os.environ["REVA_REDIS_PARALLEL_TEST_URL"]; env.update(DATABASE_URL=os.environ["REVA_PG_PARALLEL_TEST_URL"], TEST_DATABASE_URL=os.environ["REVA_PG_PARALLEL_TEST_URL"])
    run_id = runner.uuid.uuid4().hex
    monkeypatch.setattr(runner.uuid, "uuid4", lambda: SimpleNamespace(hex=run_id))
    names = [f"reva_ci_test_{run_id}_0{i}" for i in (1, 2)]
    connection = runner.connect_admin(env)
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(names[1])))
        assert runner.run(env, tmp_path / 'collision') == 1
        with connection.cursor() as cursor:
            cursor.execute('SELECT datname FROM pg_database WHERE datname = ANY(%s)', (names,))
            assert cursor.fetchall() == [(names[1],)]
    finally:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(names[1])))
        connection.close()


def test_process_timeout_terminates_child_and_still_cleans_owned_databases(tmp_path):
    import subprocess
    connection, children = Connection(), []
    class Hung:
        terminated = False
        def poll(self): return 143 if self.terminated else None
        def wait(self, timeout):
            if not self.terminated: raise subprocess.TimeoutExpired("pytest", timeout)
            return 143
        def terminate(self): self.terminated = True
    def spawn(*args, **kwargs):
        child = Hung(); children.append(child); return child
    assert runner.run(config(), tmp_path / 'timeout', connect=lambda _: connection, redis_check=lambda _: None, popen=spawn) == 1
    assert all(child.terminated for child in children)
    assert len([q for q in connection.queries if 'DROP DATABASE' in q]) == 2


def test_existing_evidence_directory_cannot_be_retried_or_overwritten(tmp_path):
    path = tmp_path / 'existing'; path.mkdir(); (path / 'summary.json').write_text('original failure')
    def must_not_connect(*args): pytest.fail('retry must be refused before connecting')
    with pytest.raises(FileExistsError): runner.run(config(), path, connect=must_not_connect, redis_check=lambda _: None)
    assert (path / 'summary.json').read_text() == 'original failure'


@pytest.mark.parametrize('url', ['redis://example.com:6379/0', 'redis://127.0.0.1:6379/13', 'redis://127.0.0.1:6379/0?host=evil', 'redis:///0', 'rediss://localhost:6379/0'])
def test_redis_endpoint_must_be_local_explicit_base(url):
    env = config(); env['REDIS_URL'] = url
    with pytest.raises(ValueError): runner.validate_environment(env)


def test_redis_unavailable_refuses_before_creating_databases(tmp_path):
    def refuse(env): raise ConnectionError('offline')
    def must_not_connect(env): pytest.fail('must check Redis before creating PostgreSQL databases')
    assert runner.run(config(), tmp_path / 'offline', connect=must_not_connect, redis_check=refuse) == 1


@pytest.mark.skipif(not (os.getenv('REVA_PG_PARALLEL_TEST_URL') and os.getenv('REVA_REDIS_PARALLEL_TEST_URL')), reason='requires dedicated local PostgreSQL and Redis test services')
def test_real_postgres_runner_does_not_overwrite_occupied_redis_database(tmp_path):
    import redis
    from urllib.parse import urlsplit, urlunsplit
    env = config()
    env.update(DATABASE_URL=os.environ['REVA_PG_PARALLEL_TEST_URL'], TEST_DATABASE_URL=os.environ['REVA_PG_PARALLEL_TEST_URL'], REDIS_URL=os.environ['REVA_REDIS_PARALLEL_TEST_URL'])
    url = urlsplit(env['REDIS_URL'])
    key = 'reva-ci-occupied:' + runner.uuid.uuid4().hex
    with redis.Redis.from_url(urlunsplit(url._replace(path='/13'))) as client:
        client.set(key, 'preserved', ex=60)
        try:
            def must_not_connect(env): pytest.fail('occupied Redis must refuse before PostgreSQL mutation')
            assert runner.run(env, tmp_path / 'occupied', connect=must_not_connect) == 1
            assert client.get(key) == b'preserved'
        finally:
            client.delete(key)


def test_second_spawn_failure_terminates_first_child_before_cleanup(tmp_path):
    connection, calls = Connection(), []
    class Live:
        terminated = False
        def poll(self): return 143 if self.terminated else None
        def terminate(self): self.terminated = True
        def wait(self, timeout): return 143
    child = Live()
    def spawn(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2: raise OSError('second spawn refused')
        return child
    assert runner.run(config(), tmp_path / 'spawn-two', connect=lambda _: connection, redis_check=lambda _: None, popen=spawn) == 1
    assert child.terminated
    assert len([q for q in connection.queries if 'DROP DATABASE' in q]) == 2
