def test_runtime_role_rejects_privileged_attributes_in_production():
    from app.services.database_security import unsafe_runtime_role_attributes

    assert unsafe_runtime_role_attributes({
        "rolsuper": True,
        "rolbypassrls": False,
        "rolcreatedb": True,
        "rolcreaterole": False,
    }) == ("rolsuper", "rolcreatedb")


def test_runtime_role_accepts_least_privilege_attributes():
    from app.services.database_security import unsafe_runtime_role_attributes

    assert unsafe_runtime_role_attributes({
        "rolsuper": False,
        "rolbypassrls": False,
        "rolcreatedb": False,
        "rolcreaterole": False,
    }) == ()


def test_authenticated_tenant_is_bound_to_request_session(db):
    from app.api.deps import bind_authenticated_tenant

    bind_authenticated_tenant(db, 42)

    assert db.info["app_user_id"] == 42


def test_scheduler_leader_sql_is_dialect_specific():
    from app.services.database_security import scheduler_leader_statements

    postgres_create, postgres_claim = scheduler_leader_statements("postgresql")
    sqlite_create, sqlite_claim = scheduler_leader_statements("sqlite")

    assert "TIMESTAMP WITH TIME ZONE" in postgres_create
    assert "NOW() - INTERVAL '5 minutes'" in postgres_claim
    assert "DEFAULT CURRENT_TIMESTAMP" in sqlite_create
    assert "datetime('now', '-5 minutes')" in sqlite_claim


def test_scheduler_leader_sql_rejects_unknown_dialect():
    from app.services.database_security import scheduler_leader_statements

    try:
        scheduler_leader_statements("mysql")
    except RuntimeError as exc:
        assert str(exc) == "unsupported_scheduler_database_dialect:mysql"
    else:
        raise AssertionError("unknown scheduler dialect must fail closed")


def test_scheduler_runtime_requires_postgresql():
    from app.services.database_security import scheduler_runtime_enabled

    assert scheduler_runtime_enabled("postgresql") is True
    assert scheduler_runtime_enabled("sqlite") is False


def test_production_migrations_require_separate_explicit_url(monkeypatch):
    from scripts.apply_managed_migrations import migration_database_url

    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    try:
        migration_database_url(
            app_env="production",
            runtime_url="postgresql://runtime/db",
        )
    except RuntimeError as exc:
        assert "MIGRATION_DATABASE_URL" in str(exc)
    else:
        raise AssertionError("production migration URL must fail closed")

    monkeypatch.setenv("MIGRATION_DATABASE_URL", "postgresql://migrator/db")
    assert migration_database_url(
        app_env="production",
        runtime_url="postgresql://runtime/db",
    ) == "postgresql://migrator/db"
