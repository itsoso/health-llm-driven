"""Disposable shared-memory SQLite with one physical connection per session.

StaticPool is unsuitable for the real Twin's concurrent sessions: another
session's close can roll back the request transaction on the shared connection.
This eval-only factory preserves concurrency without sharing DBAPI connections.
"""
import sqlite3
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool


def create_ephemeral_engine():
    from app.config import settings

    if settings.app_env != 'test':
        raise RuntimeError('full_task_eval_requires_test_in_memory_database')
    # The name is generated here, never supplied by a caller; mode=memory and
    # uri=True keep this database off disk. Each engine has a distinct namespace.
    uri = f'file:reva-eval-{uuid4().hex}?mode=memory&cache=shared'
    return create_engine(
        'sqlite://',
        creator=lambda: sqlite3.connect(uri, uri=True, check_same_thread=False),
        poolclass=QueuePool,
        pool_size=6,
        max_overflow=0,
        pool_timeout=10,
    )
