import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app.services.managed_migrations import _split_sql_statements, apply_managed_migrations


def test_apply_managed_migrations_runs_matching_dialect_once(tmp_path: Path):
    migrations_dir = tmp_path / "managed"
    migrations_dir.mkdir()
    (migrations_dir / "20260516_000001_create_example.sqlite.sql").write_text(
        """
        CREATE TABLE example_items (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE INDEX idx_example_items_name ON example_items(name);
        """,
        encoding="utf-8",
    )
    (migrations_dir / "20260516_000001_create_example.postgresql.sql").write_text(
        "CREATE TABLE should_not_run (id SERIAL PRIMARY KEY);",
        encoding="utf-8",
    )

    engine = create_engine("sqlite:///:memory:")

    first = apply_managed_migrations(engine, migrations_dir)
    second = apply_managed_migrations(engine, migrations_dir)

    tables = inspect(engine).get_table_names()
    assert [m.id for m in first.applied] == ["20260516_000001_create_example"]
    assert second.applied == []
    assert "example_items" in tables
    assert "should_not_run" not in tables
    assert "idx_example_items_name" in [i["name"] for i in inspect(engine).get_indexes("example_items")]

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM schema_migrations")).scalar_one()
    assert count == 1


def test_tokenplan_cost_migration_adds_rmb_columns(tmp_path: Path):
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    migration = migrations_dir / "20260716_120000_add_llm_usage_tokenplan_cost.sqlite.sql"
    assert migration.exists()

    isolated = tmp_path / "managed"
    isolated.mkdir()
    (isolated / migration.name).write_text(migration.read_text(encoding="utf-8"), encoding="utf-8")
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE llm_usage_logs (id INTEGER PRIMARY KEY, provider VARCHAR(32), "
            "model VARCHAR(64), prompt_tokens INTEGER, completion_tokens INTEGER, "
            "total_tokens INTEGER, cost_usd REAL)"
        ))

    result = apply_managed_migrations(engine, isolated)
    assert [migration.id for migration in result.applied] == [
        "20260716_120000_add_llm_usage_tokenplan_cost"
    ]
    columns = {column["name"] for column in inspect(engine).get_columns("llm_usage_logs")}
    assert {
        "tokenplan_credits_estimate",
        "tokenplan_cost_cny",
        "tokenplan_payg_value_cny",
        "tokenplan_cost_estimated",
        "tokenplan_cost_source",
        "tokenplan_monthly_fee_cny",
        "tokenplan_monthly_credits",
    } <= columns


def test_aigc_media_job_migrations_create_private_owner_ledger(tmp_path: Path):
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    sqlite_file = migrations_dir / "20260717_120000_create_aigc_media_jobs.sqlite.sql"
    postgres_file = migrations_dir / "20260717_120000_create_aigc_media_jobs.postgresql.sql"
    assert sqlite_file.exists()
    assert postgres_file.exists()
    assert "result_metadata JSONB" in postgres_file.read_text(encoding="utf-8")
    assert "uq_aigc_media_jobs_user_idempotency" in postgres_file.read_text(encoding="utf-8")

    isolated = tmp_path / "managed"
    isolated.mkdir()
    (isolated / sqlite_file.name).write_text(sqlite_file.read_text(encoding="utf-8"), encoding="utf-8")
    engine = create_engine("sqlite:///:memory:")
    result = apply_managed_migrations(engine, isolated)

    assert [migration.id for migration in result.applied] == ["20260717_120000_create_aigc_media_jobs"]
    columns = {column["name"] for column in inspect(engine).get_columns("aigc_media_jobs")}
    assert {
        "user_id",
        "source_message_id",
        "kind",
        "status",
        "provider_task_id",
        "request_fingerprint",
        "output_filename",
        "last_provider_checked_at",
    } <= columns
    indexes = {index["name"] for index in inspect(engine).get_indexes("aigc_media_jobs")}
    assert {"idx_aigc_media_jobs_user_created", "idx_aigc_media_jobs_user_status"} <= indexes


def test_aigc_confirmation_migrations_create_one_time_owner_ledger(tmp_path: Path):
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    sqlite_file = migrations_dir / "20260717_130000_create_aigc_media_confirmations.sqlite.sql"
    postgres_file = migrations_dir / "20260717_130000_create_aigc_media_confirmations.postgresql.sql"
    assert sqlite_file.exists()
    assert postgres_file.exists()
    assert "prompt_ciphertext TEXT NOT NULL" in postgres_file.read_text(encoding="utf-8")

    isolated = tmp_path / "managed"
    isolated.mkdir()
    (isolated / sqlite_file.name).write_text(sqlite_file.read_text(encoding="utf-8"), encoding="utf-8")
    engine = create_engine("sqlite:///:memory:")
    result = apply_managed_migrations(engine, isolated)

    assert [migration.id for migration in result.applied] == ["20260717_130000_create_aigc_media_confirmations"]
    columns = {column["name"] for column in inspect(engine).get_columns("aigc_media_confirmations")}
    assert {
        "user_id", "source_message_id", "purpose", "prompt_ciphertext", "prompt_fingerprint",
        "status", "job_id", "expires_at", "consumed_at",
    } <= columns


def test_diet_card_idempotency_migration_adds_user_scoped_unique_key(tmp_path: Path):
    from sqlalchemy.exc import IntegrityError

    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    sqlite_file = migrations_dir / "20260710_120000_add_diet_client_action_id.sqlite.sql"
    postgres_file = migrations_dir / "20260710_120000_add_diet_client_action_id.postgresql.sql"
    assert sqlite_file.exists()
    assert postgres_file.exists()
    assert "WHERE client_action_id IS NOT NULL" in postgres_file.read_text(encoding="utf-8")

    isolated = tmp_path / "managed"
    isolated.mkdir()
    (isolated / sqlite_file.name).write_text(
        sqlite_file.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE diet_records (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)"))
    result = apply_managed_migrations(engine, isolated)
    assert [migration.id for migration in result.applied] == [
        "20260710_120000_add_diet_client_action_id"
    ]

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO diet_records (id, user_id, client_action_id) "
            "VALUES (1, 7, 'card-1'), (2, 8, 'card-1')"
        ))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO diet_records (id, user_id, client_action_id) "
                "VALUES (3, 7, 'card-1')"
            ))


def test_action_card_accepted_key_migration_enforces_unique_replay_key(tmp_path: Path):
    from sqlalchemy.exc import IntegrityError

    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    sqlite_file = migrations_dir / "20260714_170000_add_action_card_accepted_create_key.sqlite.sql"
    postgres_file = migrations_dir / "20260714_170000_add_action_card_accepted_create_key.postgresql.sql"
    assert sqlite_file.exists()
    assert postgres_file.exists()
    assert "WHERE accepted_create_key IS NOT NULL" in postgres_file.read_text(encoding="utf-8")

    isolated = tmp_path / "managed"
    isolated.mkdir()
    (isolated / sqlite_file.name).write_text(sqlite_file.read_text(encoding="utf-8"), encoding="utf-8")
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE action_cards (id INTEGER PRIMARY KEY)"))

    result = apply_managed_migrations(engine, isolated)
    assert [migration.id for migration in result.applied] == [
        "20260714_170000_add_action_card_accepted_create_key"
    ]

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO action_cards (id, accepted_create_key) VALUES (1, 'same-key')"
        ))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO action_cards (id, accepted_create_key) VALUES (2, 'same-key')"
            ))


def test_intervention_event_idempotency_migration_enforces_unique_replay_key(tmp_path: Path):
    from sqlalchemy.exc import IntegrityError

    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    sqlite_file = migrations_dir / "20260714_171000_add_intervention_event_idempotency_key.sqlite.sql"
    postgres_file = migrations_dir / "20260714_171000_add_intervention_event_idempotency_key.postgresql.sql"
    assert sqlite_file.exists()
    assert postgres_file.exists()
    assert "WHERE event_idempotency_key IS NOT NULL" in postgres_file.read_text(encoding="utf-8")

    isolated = tmp_path / "managed"
    isolated.mkdir()
    (isolated / sqlite_file.name).write_text(sqlite_file.read_text(encoding="utf-8"), encoding="utf-8")
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE intervention_events (id INTEGER PRIMARY KEY)"))

    result = apply_managed_migrations(engine, isolated)
    assert [migration.id for migration in result.applied] == [
        "20260714_171000_add_intervention_event_idempotency_key"
    ]

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO intervention_events (id, event_idempotency_key) VALUES (1, 'same-key')"
        ))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO intervention_events (id, event_idempotency_key) VALUES (2, 'same-key')"
            ))


def test_food_calibration_names_migration_defaults_closed_and_curates_known_rows(tmp_path: Path):
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    sqlite_file = migrations_dir / "20260711_201000_add_food_calibration_names.sqlite.sql"
    postgres_file = migrations_dir / "20260711_201000_add_food_calibration_names.postgresql.sql"
    assert sqlite_file.exists()
    assert postgres_file.exists()

    isolated = tmp_path / "managed"
    isolated.mkdir()
    (isolated / sqlite_file.name).write_text(
        sqlite_file.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE food_items (food_id VARCHAR(120) PRIMARY KEY, "
            "canonical_name VARCHAR(200) NOT NULL, aliases JSON NOT NULL DEFAULT '[]')"
        ))
        conn.execute(text(
            "INSERT INTO food_items (food_id, canonical_name) VALUES "
            "('cfc:tofu_firm', '豆腐'), ('custom:unknown', '自定义食物')"
        ))

    result = apply_managed_migrations(engine, isolated)

    assert [migration.id for migration in result.applied] == [
        "20260711_201000_add_food_calibration_names"
    ]
    with engine.connect() as conn:
        tofu = conn.execute(text(
            "SELECT calibration_names FROM food_items WHERE food_id='cfc:tofu_firm'"
        )).scalar_one()
        unknown = conn.execute(text(
            "SELECT calibration_names FROM food_items WHERE food_id='custom:unknown'"
        )).scalar_one()
    assert json.loads(tofu) == ["北豆腐", "老豆腐"]
    assert json.loads(unknown) == []


def test_split_sql_statements_keeps_postgres_dollar_quoted_blocks_intact():
    statements = _split_sql_statements(
        """
        -- Semicolons inside the DO block must not split the statement.
        DO $$
        BEGIN
            RAISE NOTICE 'first';
            RAISE NOTICE 'second';
        END $$;

        CREATE TABLE example_items (
            id SERIAL PRIMARY KEY
        );
        """
    )

    assert len(statements) == 2
    assert statements[0].startswith("DO $$")
    assert statements[0].endswith("END $$")
    assert statements[1].startswith("CREATE TABLE example_items")


def test_managed_system_knowledge_migration_creates_phase0_tables():
    """验证 KB phase0 migration 在 sqlite 上能正常 CREATE 三张表 + 索引.

    不跑全量 managed_migrations: 其它 ALTER 类 migration (如 add_detected_source)
    假定 ORM 表已建好, 而 ORM create_all 又会把本测试想验证的 kb_* 表先建出来 —
    两难. 直接对 phase0 这份 sqlite 文件跑 SQL 即可.
    """
    engine = create_engine("sqlite:///:memory:")
    migration_file = (
        Path(__file__).resolve().parents[1]
        / "migrations" / "managed"
        / "20260516_200000_create_system_knowledge_tables.sqlite.sql"
    )
    sql = migration_file.read_text(encoding="utf-8")
    with engine.begin() as conn:
        for stmt in sql.split(";"):
            s = stmt.strip()
            if s:
                conn.execute(text(s))

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "kb_documents" in tables
    assert "kb_edges" in tables
    assert "kb_audit" in tables
    assert "ix_kb_documents_entity" in [i["name"] for i in inspector.get_indexes("kb_documents")]
    assert "ix_kb_edges_src_relation" in [i["name"] for i in inspector.get_indexes("kb_edges")]


def test_managed_action_cards_graded_at_index_migration(tmp_path: Path):
    """ActionCard graded_at window probes must have a managed partial index."""
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    sqlite_file = migrations_dir / "20260521_121000_add_action_cards_graded_at_index.sqlite.sql"
    postgres_file = migrations_dir / "20260521_121000_add_action_cards_graded_at_index.postgresql.sql"

    assert sqlite_file.exists()
    assert postgres_file.exists()
    assert "WHERE graded_at IS NOT NULL" in postgres_file.read_text(encoding="utf-8")

    isolated_dir = tmp_path / "managed"
    isolated_dir.mkdir()
    (isolated_dir / sqlite_file.name).write_text(sqlite_file.read_text(encoding="utf-8"), encoding="utf-8")

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE action_cards (id INTEGER PRIMARY KEY, graded_at TIMESTAMP)"))

    result = apply_managed_migrations(engine, isolated_dir)

    assert "20260521_121000_add_action_cards_graded_at_index" in [m.id for m in result.applied]
    indexes = inspect(engine).get_indexes("action_cards")
    assert "idx_action_cards_graded_at_not_null" in [i["name"] for i in indexes]


def test_desktop_jobs_has_managed_postgres_migration():
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    postgres_file = migrations_dir / "20260523_120000_create_desktop_jobs.postgresql.sql"

    assert postgres_file.exists()
    sql = postgres_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS desktop_jobs" in sql
    assert "idx_desktop_jobs_user_created" in sql
    assert "idx_desktop_jobs_user_status" in sql


def test_adherence_writeback_unique_migrations_exist_and_dedupe():
    """依从写回幂等迁移成对存在,PG variant 先 dedup 再建唯一索引(脏数据上直接建会失败)。"""
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"

    med_pg = migrations_dir / "20260617_120000_add_medication_log_unique.postgresql.sql"
    med_sqlite = migrations_dir / "20260617_120000_add_medication_log_unique.sqlite.sql"
    supp_pg = migrations_dir / "20260617_120100_add_supplement_record_unique.postgresql.sql"
    supp_sqlite = migrations_dir / "20260617_120100_add_supplement_record_unique.sqlite.sql"
    for f in (med_pg, med_sqlite, supp_pg, supp_sqlite):
        assert f.exists(), f"缺迁移文件: {f.name}"

    med_pg_sql = med_pg.read_text(encoding="utf-8")
    # PG 先删现存重复(同槽保留 max id)再建唯一索引;COALESCE 让 NULL 槽去重、多剂不同时点并存。
    assert "DELETE FROM medication_logs" in med_pg_sql
    assert "a.id < b.id" in med_pg_sql
    assert "COALESCE(taken_time, '')" in med_pg_sql
    assert "uq_medlog_med_date_time" in med_pg_sql

    supp_pg_sql = supp_pg.read_text(encoding="utf-8")
    assert "DELETE FROM supplement_records" in supp_pg_sql
    assert "uq_supprec_supp_date" in supp_pg_sql

    # 注释里不能出现裸分号(runner 按 ; 切分,会把语句切碎)。
    for f in (med_pg, med_sqlite, supp_pg, supp_sqlite):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("--"):
                assert ";" not in line, f"{f.name} 注释含裸分号会被 runner 误切: {line!r}"


def test_medication_log_unique_sqlite_migration_creates_index(tmp_path: Path):
    """对裸 medication_logs 表跑 sqlite migration → 建出 uq_medlog_med_date_time 唯一索引。

    用 IntegrityError 功能验证而非 inspect().get_indexes():SQLAlchemy 反射会跳过
    expression-based index(COALESCE(...)),反射查不到不代表没建。NULL 折叠去重 + 多剂并存
    一并钉死。
    """
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    sqlite_file = migrations_dir / "20260617_120000_add_medication_log_unique.sqlite.sql"

    isolated = tmp_path / "managed"
    isolated.mkdir()
    (isolated / sqlite_file.name).write_text(sqlite_file.read_text(encoding="utf-8"), encoding="utf-8")

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE medication_logs (id INTEGER PRIMARY KEY, medication_id INTEGER, "
            "taken_date DATE, taken_time VARCHAR(10), status VARCHAR(20))"
        ))

    result = apply_managed_migrations(engine, isolated)
    assert "20260617_120000_add_medication_log_unique" in [m.id for m in result.applied]
    # 索引名应在 sqlite_master(反射跳过表达式索引,这里直接看建表目录)。
    with engine.connect() as conn:
        names = [r[0] for r in conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='index'")).fetchall()]
    assert "uq_medlog_med_date_time" in names

    ins = (
        "INSERT INTO medication_logs (medication_id, taken_date, taken_time, status) "
        "VALUES (1, '2026-06-17', :t, 'taken')"
    )
    with engine.begin() as conn:
        conn.execute(text(ins), {"t": None})        # 按日标记(NULL)
    # 同 (药, 日期, NULL→'') 第二条应撞唯一约束
    with pytest.raises(SAIntegrityError):
        with engine.begin() as conn:
            conn.execute(text(ins), {"t": None})
    # 不同时点是不同槽 → 允许(多剂不被误伤)
    with engine.begin() as conn:
        conn.execute(text(ins), {"t": "08:00"})
        conn.execute(text(ins), {"t": "20:00"})


def test_semicolon_inside_comment_does_not_break_statement(tmp_path: Path):
    """注释里出现 ; 不能把后面的真语句切断(踩过:garmin 约束迁移中文注释含 ;)。"""
    migrations_dir = tmp_path / "managed"
    migrations_dir.mkdir()
    (migrations_dir / "20260609_000001_comment_semicolon.sqlite.sql").write_text(
        """
        -- 这条注释里故意放一个分号; 看是否会把下面的建表语句切断
        -- 多行注释; 再来一个分号
        CREATE TABLE comment_semi (id INTEGER PRIMARY KEY, name TEXT);
        """,
        encoding="utf-8",
    )

    engine = create_engine("sqlite:///:memory:")
    result = apply_managed_migrations(engine, migrations_dir)

    assert [m.id for m in result.applied] == ["20260609_000001_comment_semicolon"]
    assert "comment_semi" in inspect(engine).get_table_names()


def test_retire_legacy_agent_table_names_sqlite_migration_preserves_data(tmp_path: Path):
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    sqlite_file = migrations_dir / "20260704_200000_retire_legacy_agent_table_names.sqlite.sql"
    postgres_file = migrations_dir / "20260704_200000_retire_legacy_agent_table_names.postgresql.sql"

    assert sqlite_file.exists()
    assert postgres_file.exists()

    isolated = tmp_path / "managed"
    isolated.mkdir()
    (isolated / sqlite_file.name).write_text(sqlite_file.read_text(encoding="utf-8"), encoding="utf-8")

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY)"
        ))
        conn.execute(text(
            "CREATE TABLE openclaw_conversations ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT, updated_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE openclaw_messages ("
            "id INTEGER PRIMARY KEY, conversation_id INTEGER NOT NULL, role TEXT, content TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE health_trend_reports ("
            "id INTEGER PRIMARY KEY, openclaw_batch_id TEXT)"
        ))
        conn.execute(text(
            "INSERT INTO openclaw_conversations (id, user_id, title, updated_at) "
            "VALUES (10, 3, '阿衡', '2026-07-04 12:00:00')"
        ))
        conn.execute(text(
            "INSERT INTO openclaw_messages (id, conversation_id, role, content) "
            "VALUES (20, 10, 'assistant', 'ok')"
        ))
        conn.execute(text(
            "INSERT INTO health_trend_reports (id, openclaw_batch_id) VALUES (30, 'batch-1')"
        ))

    result = apply_managed_migrations(engine, isolated)

    assert [m.id for m in result.applied] == ["20260704_200000_retire_legacy_agent_table_names"]
    tables = inspect(engine).get_table_names()
    assert "agent_conversations" in tables
    assert "agent_messages" in tables
    assert "openclaw_conversations" not in tables
    assert "openclaw_messages" not in tables
    assert "analysis_batch_id" in [c["name"] for c in inspect(engine).get_columns("health_trend_reports")]
    assert "openclaw_batch_id" not in [c["name"] for c in inspect(engine).get_columns("health_trend_reports")]

    with engine.connect() as conn:
        title = conn.execute(text("SELECT title FROM agent_conversations WHERE id = 10")).scalar_one()
        content = conn.execute(text("SELECT content FROM agent_messages WHERE id = 20")).scalar_one()
        batch_id = conn.execute(text("SELECT analysis_batch_id FROM health_trend_reports WHERE id = 30")).scalar_one()
    assert title == "阿衡"
    assert content == "ok"
    assert batch_id == "batch-1"


def test_agent_client_turn_sqlite_migration_enforces_scoped_user_uniqueness(tmp_path: Path):
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    sqlite_file = migrations_dir / "20260709_120000_add_agent_client_turn_id.sqlite.sql"
    postgres_file = migrations_dir / "20260709_120000_add_agent_client_turn_id.postgresql.sql"
    assert sqlite_file.exists()
    assert postgres_file.exists()

    isolated = tmp_path / "managed"
    isolated.mkdir()
    (isolated / sqlite_file.name).write_text(sqlite_file.read_text(encoding="utf-8"), encoding="utf-8")
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE agent_messages ("
            "id INTEGER PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL)"
        ))

    result = apply_managed_migrations(engine, isolated)

    assert [m.id for m in result.applied] == ["20260709_120000_add_agent_client_turn_id"]
    assert "client_turn_id" in {column["name"] for column in inspect(engine).get_columns("agent_messages")}
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO agent_messages (id, role, content, client_turn_id) "
            "VALUES (1, 'user', 'a', '1:turn-same'), (2, 'user', 'b', '2:turn-same')"
        ))
    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO agent_messages (id, role, content, client_turn_id) "
                "VALUES (3, 'user', 'duplicate', '1:turn-same')"
            ))
