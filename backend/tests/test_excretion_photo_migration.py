"""Managed DDL preserves historical rows and owner-scoped nullable request keys."""
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from app.services.managed_migrations import apply_managed_migrations


@pytest.mark.parametrize('dialect', ['sqlite', 'postgresql'])
def test_excretion_photo_migration(dialect, tmp_path):
    pg_url = os.environ.get('TEST_DATABASE_URL')
    if dialect == 'postgresql' and not pg_url:
        pytest.skip('requires isolated PostgreSQL TEST_DATABASE_URL')
    if dialect == 'postgresql':
        url = make_url(pg_url)
        if url.get_backend_name() != 'postgresql' or 'test' not in (url.database or ''):
            raise RuntimeError('migration tests require an isolated PostgreSQL test database')
    engine = create_engine(pg_url if dialect == 'postgresql' else 'sqlite:///:memory:')
    isolated = tmp_path / 'migrations'
    isolated.mkdir()
    name = f'20261011_120000_excretion_private_photo.{dialect}.sql'
    source = Path(__file__).parents[1] / 'migrations' / 'managed' / name
    (isolated / name).write_text(source.read_text())
    try:
        with engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS excretion_records'))
            conn.execute(text('DROP TABLE IF EXISTS schema_migrations'))
            blood_default = ' DEFAULT FALSE' if dialect == 'postgresql' else ''
            conn.execute(text(f'CREATE TABLE excretion_records (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, blood_present BOOLEAN{blood_default})'))
            conn.execute(text('INSERT INTO excretion_records (id, user_id, blood_present) VALUES (1, 1, NULL), (2, 1, TRUE)'))
        apply_managed_migrations(engine, isolated)
        apply_managed_migrations(engine, isolated)
        with engine.begin() as conn:
            rows = conn.execute(text('SELECT id, blood_present, photo_key, client_request_id, client_request_hash FROM excretion_records ORDER BY id')).all()
            assert rows[0] == (1, None, None, None, None)
            assert bool(rows[1][1]) is True
            conn.execute(text("INSERT INTO excretion_records (id,user_id,client_request_id) VALUES (3,1,'same'),(4,2,'same'),(5,1,NULL),(6,1,NULL)"))
            assert conn.execute(text('SELECT blood_present FROM excretion_records WHERE id=3')).scalar() is None
            if dialect == 'postgresql':
                conn.execute(text('SET LOCAL enable_seqscan = off'))
                plan = conn.execute(text("EXPLAIN SELECT id FROM excretion_records WHERE user_id=1 AND client_request_id='same'")).scalars().all()
                assert any('uq_excretion_user_client_request' in line for line in plan)
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO excretion_records (id,user_id,client_request_id) VALUES (7,1,'same')"))
    finally:
        with engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS excretion_records'))
            conn.execute(text('DROP TABLE IF EXISTS schema_migrations'))
        engine.dispose()
