"""SQLite test/runtime engine pooling contracts."""

from sqlalchemy.pool import StaticPool


def test_in_memory_sqlite_engine_uses_one_cross_thread_connection():
    from app.database import engine

    assert isinstance(engine.pool, StaticPool)
