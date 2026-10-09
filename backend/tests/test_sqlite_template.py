"""SQLite templates must preserve fresh-database fixture semantics."""
import logging
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from tests.sqlite_template import SQLiteTemplate


def schema():
    metadata = MetaData()
    Table('items', metadata, Column('id', Integer, primary_key=True))
    return metadata


def test_commits_rollbacks_and_arbitrary_ddl_do_not_leak():
    m = schema()
    with SQLiteTemplate() as factory:
        with factory.database(m) as first:
            with sessionmaker(bind=first)() as session:
                session.execute(text('insert into items values (1)'))
                session.commit()
                session.execute(text('insert into items values (2)'))
                session.rollback()
            with first.begin() as c:
                c.exec_driver_sql('create table extra(id integer)')
        with factory.database(m) as second:
            assert first is not second
            with second.connect() as c:
                assert c.exec_driver_sql('select count(*) from items').scalar() == 0
                assert not inspect(c).has_table('extra')
                assert c.exec_driver_sql('PRAGMA foreign_keys').scalar() == 0


def test_dynamic_metadata_invalidates_template():
    m = schema()
    with SQLiteTemplate() as factory:
        with factory.database(m):
            pass
        late = Table('late', m, Column('id', Integer, primary_key=True))
        with factory.database(m) as engine:
            assert inspect(engine).has_table('late')
        m.remove(late)
        with factory.database(m) as engine:
            assert not inspect(engine).has_table('late')


def test_changed_column_rebuilds_even_with_same_table_identity():
    m = schema()
    with SQLiteTemplate() as factory:
        with factory.database(m):
            pass
        m.tables['items'].append_column(Column('new_column', Integer))
        with factory.database(m) as engine:
            assert 'new_column' in {c['name'] for c in inspect(engine).get_columns('items')}


@pytest.mark.parametrize('scope', ['metadata', 'table', 'column'])
def test_ddl_listeners_fall_back_and_are_not_suppressed(scope, caplog):
    m = schema(); calls = []
    target = {'metadata': m, 'table': m.tables['items'], 'column': m.tables['items'].c.id}[scope]
    event.listen(target, 'after_create', lambda *a, **k: calls.append('create'))
    event.listen(target, 'after_drop', lambda *a, **k: calls.append('drop'))
    with caplog.at_level(logging.INFO), SQLiteTemplate() as factory:
        for _ in range(2):
            with factory.database(m):
                pass
    if scope != 'column':
        assert calls.count('create') == 2
        assert calls.count('drop') >= 2
    assert 'sqlite template bypass: schema event listener' in caplog.text


def test_custom_global_connection_event_uses_ddl_path(caplog):
    m = schema(); seen = []
    def connected(connection):
        seen.append(connection.engine)
    event.listen(Engine, 'engine_connect', connected)
    try:
        with caplog.at_level(logging.INFO), SQLiteTemplate() as factory:
            with factory.database(m) as engine:
                assert inspect(engine).has_table('items')
                assert engine in seen
        assert 'sqlite template bypass: engine event listener' in caplog.text
    finally:
        event.remove(Engine, 'engine_connect', connected)


def test_thread_access_uses_same_database_and_parallel_clones_are_isolated():
    m = schema()
    with SQLiteTemplate() as factory:
        def run(value):
            with factory.database(m) as engine:
                with engine.begin() as c:
                    c.exec_driver_sql('insert into items values (?)', (value,))
                def read():
                    with engine.connect() as c:
                        return c.exec_driver_sql('select id from items').scalar()
                with ThreadPoolExecutor(max_workers=1) as inner:
                    return inner.submit(read).result()
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert list(executor.map(run, [11, 22])) == [11, 22]


def test_cleanup_after_test_failure_and_backup_failure(monkeypatch):
    m = schema()
    with SQLiteTemplate() as factory:
        with pytest.raises(ValueError, match='test failed'):
            with factory.database(m) as first:
                with first.begin() as c:
                    c.exec_driver_sql('insert into items values (1)')
                raise ValueError('test failed')
        with first.connect() as c:
            assert not inspect(c).has_table('items')
        def broken(*args):
            raise RuntimeError('backup failed')
        monkeypatch.setattr(factory, '_backup', broken)
        with pytest.raises(RuntimeError, match='backup failed'):
            with factory.database(m):
                pytest.fail('must never yield after failed backup')


def test_listener_added_during_test_still_observes_teardown(caplog):
    m = schema(); drops = []
    with caplog.at_level(logging.INFO), SQLiteTemplate() as factory:
        with factory.database(m):
            event.listen(m, 'after_drop', lambda *a, **k: drops.append(True))
    assert drops == [True]
    assert 'sqlite template bypass: schema event listener' in caplog.text


def test_custom_pool_connect_event_keeps_pragma(caplog):
    from sqlalchemy.pool import Pool
    m = schema()
    def setup(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')
    event.listen(Pool, 'connect', setup)
    try:
        with caplog.at_level(logging.INFO), SQLiteTemplate() as factory:
            with factory.database(m) as engine:
                with engine.connect() as c:
                    assert c.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
        assert 'sqlite template bypass: pool event listener' in caplog.text
    finally:
        event.remove(Pool, 'connect', setup)


def test_conditional_ddl_is_never_cached(caplog):
    from sqlalchemy import Index
    m = schema()
    enabled = [False]
    Index('conditional_index', m.tables['items'].c.id).ddl_if(callable_=lambda *a, **k: enabled[0])
    with caplog.at_level(logging.INFO), SQLiteTemplate() as factory:
        with factory.database(m) as engine:
            assert not inspect(engine).get_indexes('items')
        enabled[0] = True
        with factory.database(m) as engine:
            assert inspect(engine).get_indexes('items')[0]['name'] == 'conditional_index'
    assert 'sqlite template bypass: conditional DDL' in caplog.text


def test_compiled_types_constraints_indexes_and_values_match_fresh_schema():
    import datetime
    from decimal import Decimal
    from sqlalchemy import DateTime, ForeignKey, Index, JSON, LargeBinary, Numeric, String, UniqueConstraint
    from sqlalchemy.exc import IntegrityError
    m = schema()
    child = Table('child', m, Column('id', Integer, primary_key=True),
                  Column('parent', ForeignKey('items.id')), Column('label', String, nullable=False),
                  Column('payload', JSON), Column('amount', Numeric(10, 2)),
                  Column('created', DateTime), Column('blob', LargeBinary), UniqueConstraint('label'))
    Index('child_parent_idx', child.c.parent)
    now = datetime.datetime(2026, 1, 2, 3, 4, 5)
    with SQLiteTemplate() as factory:
        for _ in range(2):
            with factory.database(m) as engine:
                assert inspect(engine).get_foreign_keys('child')[0]['referred_table'] == 'items'
                assert inspect(engine).get_indexes('child')[0]['name'] == 'child_parent_idx'
                with engine.begin() as c:
                    c.execute(child.insert().values(label='x', payload={'a': [1]}, amount=Decimal('2.30'), created=now, blob=b'bytes'))
                    row = c.execute(child.select()).mappings().one()
                    assert row['id'] == 1
                    assert (row['payload'], row['amount'], row['created'], row['blob']) == ({'a': [1]}, Decimal('2.30'), now, b'bytes')
                    with pytest.raises(IntegrityError):
                        c.execute(child.insert().values(label='x'))


def test_invalid_postgres_setting_still_rejected_before_template(monkeypatch):
    from tests import conftest
    class RejectTemplate:
        def database(self, metadata):
            pytest.fail('PostgreSQL branch must never use SQLite template')
    for url in ('sqlite:///:memory:', 'postgresql://localhost/production'):
        monkeypatch.setenv('TEST_DATABASE_URL', url)
        generator = conftest.db.__wrapped__(RejectTemplate())
        with pytest.raises(RuntimeError, match='PostgreSQL database'):
            next(generator)


def test_builtin_sqlite_enum_hooks_are_proven_noops_and_still_clone(monkeypatch):
    from sqlalchemy import Enum
    m = schema()
    m.tables['items'].append_column(Column('state', Enum('a', 'b', native_enum=False)))
    with SQLiteTemplate() as factory:
        calls = []
        original = factory._backup
        monkeypatch.setattr(factory, '_backup', lambda *args: (calls.append(True), original(*args))[-1])
        for _ in range(2):
            with factory.database(m) as engine:
                with engine.begin() as c:
                    c.execute(m.tables['items'].insert().values(state='a'))
                    assert c.execute(m.tables['items'].select()).mappings().one()['state'] == 'a'
        assert calls == [True, True]


def test_custom_enum_hook_cannot_be_suppressed(caplog):
    from sqlalchemy import Enum
    calls = []
    class CustomEnum(Enum):
        def _on_metadata_create(self, target, bind, **kw):
            calls.append(True)
            super()._on_metadata_create(target, bind, **kw)
    m = schema()
    m.tables['items'].append_column(Column('state', CustomEnum('a', 'b', native_enum=False)))
    with caplog.at_level(logging.INFO), SQLiteTemplate() as factory:
        for _ in range(2):
            with factory.database(m):
                pass
    assert len(calls) == 2
    assert 'sqlite template bypass: schema event listener' in caplog.text


def test_patched_builtin_enum_hook_is_not_treated_as_noop(monkeypatch, caplog):
    from sqlalchemy import Enum
    from sqlalchemy.sql.sqltypes import SchemaType
    m = schema(); calls = []
    m.tables['items'].append_column(Column('state', Enum('a', 'b', native_enum=False)))
    original = SchemaType._on_metadata_create
    def changed(self, *args, **kwargs):
        calls.append(True)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(SchemaType, '_on_metadata_create', changed)
    with caplog.at_level(logging.INFO), SQLiteTemplate() as factory:
        for _ in range(2):
            with factory.database(m):
                pass
    assert len(calls) == 2
    assert 'sqlite template bypass: schema event listener' in caplog.text
