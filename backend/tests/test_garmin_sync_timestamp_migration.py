"""Preserve the legacy UTC read contract while correcting future aware writes."""
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.services.managed_migrations import apply_managed_migrations


MIGRATION = '20261012_110000_garmin_sync_timestamp_timezone'


@pytest.mark.parametrize('dialect', ['sqlite', 'postgresql'])
def test_garmin_timestamp_migration_preserves_legacy_values_and_fixes_aware_writes(dialect, tmp_path):
    pg_url = os.environ.get('TEST_DATABASE_URL')
    if dialect == 'postgresql':
        if not pg_url:
            pytest.skip('isolated PostgreSQL TEST_DATABASE_URL required')
        url = make_url(pg_url)
        if url.get_backend_name() != 'postgresql' or 'test' not in (url.database or ''):
            raise RuntimeError('isolated PostgreSQL test database required')
    engine = create_engine(pg_url if dialect == 'postgresql' else 'sqlite:///:memory:')
    directory = tmp_path / 'migrations'
    directory.mkdir()
    name = f'{MIGRATION}.{dialect}.sql'
    source = Path(__file__).parents[1] / 'migrations' / 'managed' / name
    # Before the migration exists, exercise the unchanged database and fail on
    # its real column semantics rather than counting a missing file as RED.
    if source.exists():
        (directory / name).write_text(source.read_text())
    instant = datetime(2026, 10, 12, 2, tzinfo=UTC)
    try:
        with engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS garmin_credentials CASCADE' if dialect == 'postgresql' else 'DROP TABLE IF EXISTS garmin_credentials'))
            conn.execute(text('DROP TABLE IF EXISTS schema_migrations'))
            conn.execute(text('CREATE TABLE garmin_credentials (id INTEGER PRIMARY KEY, last_sync_at TIMESTAMP NULL)'))
            conn.execute(text("INSERT INTO garmin_credentials VALUES (1, '2026-10-12 10:00:00'), (2, NULL)"))
            if dialect == 'postgresql':
                conn.execute(text("SET LOCAL TIMEZONE = 'Asia/Shanghai'"))
                conn.execute(text('INSERT INTO garmin_credentials VALUES (3, :value)'), {'value': instant})
                old = conn.execute(text('SELECT last_sync_at FROM garmin_credentials WHERE id=3')).scalar()
                assert old.replace(tzinfo=UTC) == instant + timedelta(hours=8)
        first = apply_managed_migrations(engine, directory)
        second = apply_managed_migrations(engine, directory)
        with engine.begin() as conn:
            if dialect == 'postgresql':
                kind = conn.execute(text("SELECT data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='garmin_credentials' AND column_name='last_sync_at'")).scalar()
                assert kind == 'timestamp with time zone'
                conn.execute(text("SET LOCAL TIMEZONE = 'Asia/Shanghai'"))
                old = conn.execute(text('SELECT last_sync_at FROM garmin_credentials WHERE id=1')).scalar()
                assert old.astimezone(UTC) == datetime(2026, 10, 12, 10, tzinfo=UTC)
                # Ambiguous historical values keep their existing application
                # interpretation. The migration does not guess an 8h correction.
                assert conn.execute(text('SELECT last_sync_at FROM garmin_credentials WHERE id=3')).scalar().astimezone(UTC) == instant + timedelta(hours=8)
                conn.execute(text('INSERT INTO garmin_credentials VALUES (4, :value)'), {'value': instant})
                assert conn.execute(text('SELECT last_sync_at FROM garmin_credentials WHERE id=4')).scalar().astimezone(UTC) == instant
                # Already-correct columns remain idempotent even without the ledger.
                conn.execute(text('DELETE FROM schema_migrations'))
            else:
                assert conn.execute(text('SELECT last_sync_at FROM garmin_credentials WHERE id=1')).scalar() == '2026-10-12 10:00:00'
            assert conn.execute(text('SELECT last_sync_at FROM garmin_credentials WHERE id=2')).scalar() is None
        assert len(first.applied) == 1 and not second.applied and len(second.skipped) == 1
        if dialect == 'postgresql':
            apply_managed_migrations(engine, directory)
            with engine.begin() as conn:
                conn.execute(text("SET LOCAL TIMEZONE = 'Asia/Shanghai'"))
                down = source.with_name(f'{MIGRATION}.down.postgresql.sql')
                conn.exec_driver_sql(down.read_text())
                assert conn.execute(text('SELECT last_sync_at FROM garmin_credentials WHERE id=4')).scalar() == instant.replace(tzinfo=None)
                assert conn.execute(text('SELECT last_sync_at FROM garmin_credentials WHERE id=2')).scalar() is None
                conn.exec_driver_sql(source.read_text())
                assert conn.execute(text('SELECT last_sync_at FROM garmin_credentials WHERE id=4')).scalar().astimezone(UTC) == instant
                assert conn.execute(text('SELECT last_sync_at FROM garmin_credentials WHERE id=1')).scalar().astimezone(UTC) == datetime(2026, 10, 12, 10, tzinfo=UTC)
    finally:
        with engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS garmin_credentials CASCADE' if dialect == 'postgresql' else 'DROP TABLE IF EXISTS garmin_credentials'))
            conn.execute(text('DROP TABLE IF EXISTS schema_migrations'))
        engine.dispose()


@pytest.mark.parametrize('connection_timezone', ['UTC', 'Asia/Shanghai'])
def test_credential_status_preserves_legacy_instant_and_accepts_new_aware_writes(connection_timezone, tmp_path):
    from sqlalchemy.orm import Session
    from app.api.data_collection import get_credential_status
    from app.models.user import GarminCredential, User

    pg_url = os.environ.get('TEST_DATABASE_URL')
    if not pg_url:
        pytest.skip('isolated PostgreSQL TEST_DATABASE_URL required')
    url = make_url(pg_url)
    if url.get_backend_name() != 'postgresql' or 'test' not in (url.database or ''):
        raise RuntimeError('isolated PostgreSQL test database required')
    engine = create_engine(pg_url, connect_args={'options': f'-c timezone={connection_timezone}'})
    directory = tmp_path / 'api-migrations'
    directory.mkdir()
    name = f'{MIGRATION}.postgresql.sql'
    source = Path(__file__).parents[1] / 'migrations' / 'managed' / name
    (directory / name).write_text(source.read_text())
    try:
        with engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS garmin_credentials CASCADE'))
            conn.execute(text('DROP TABLE IF EXISTS users CASCADE'))
            conn.execute(text('DROP TABLE IF EXISTS schema_migrations'))
        User.__table__.create(engine)
        GarminCredential.__table__.create(engine)
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE garmin_credentials ALTER COLUMN last_sync_at TYPE TIMESTAMP WITHOUT TIME ZONE USING last_sync_at AT TIME ZONE 'UTC'"))
        instant = datetime.now(UTC) - timedelta(minutes=5)
        with Session(engine) as session:
            user = User(username='migration_status', email='migration_status@example.com', hashed_password='synthetic', name='Synthetic')
            session.add(user)
            session.flush()
            user_id = user.id
            cred = GarminCredential(user_id=user_id, garmin_email='synthetic@example.com', encrypted_password='synthetic', credentials_valid=True, last_sync_at=instant.replace(tzinfo=None))
            session.add(cred)
            session.commit()
            before = get_credential_status(current_user=session.get(User, user_id), db=session)
            session.commit()  # Do not hold a read lock while applying managed DDL.
        apply_managed_migrations(engine, directory)
        with Session(engine) as session:
            user = session.get(User, user_id)
            after = get_credential_status(current_user=user, db=session)
            assert before['health'] == after['health'] == 'healthy'
            assert before['minutes_since_last_sync'] == after['minutes_since_last_sync'] == 5
            assert datetime.fromisoformat(after['last_sync_at']).astimezone(UTC) == instant
            assert datetime.fromisoformat(before['last_sync_at']).replace(tzinfo=UTC) == instant
            cred = session.query(GarminCredential).filter(GarminCredential.user_id == user_id).one()
            cred.last_sync_at = instant
            session.commit()
            new = get_credential_status(current_user=user, db=session)
            assert new['health'] == 'healthy' and new['minutes_since_last_sync'] == 5
            assert datetime.fromisoformat(new['last_sync_at']).astimezone(UTC) == instant
    finally:
        with engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS garmin_credentials CASCADE'))
            conn.execute(text('DROP TABLE IF EXISTS users CASCADE'))
            conn.execute(text('DROP TABLE IF EXISTS schema_migrations'))
        engine.dispose()
