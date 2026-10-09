"""Clone empty SQLite schemas while retaining a fresh engine per test.

Only plain, event-free SQLite schemas use the optimization. Custom SQLAlchemy
listeners retain the original drop/create/drop lifecycle, with a logged reason.
PostgreSQL fixtures never use this helper. No test data is cached.
"""
from contextlib import contextmanager
import hashlib
import logging
from threading import RLock

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.sql.sqltypes import Enum, SchemaType
from sqlalchemy.util.langhelpers import portable_instancemethod

logger = logging.getLogger(__name__)
_ENUM_HOOKS = {name: getattr(SchemaType, name) for name in (
    '_on_metadata_create', '_on_metadata_drop', '_on_table_create', '_on_table_drop',
)}
_ENUM_VARIANT_CHECK = SchemaType._is_impl_for_variant
_ENUM_DIALECT_IMPL = Enum.dialect_impl
_DDL_EVENTS = ('before_create', 'after_create', 'before_drop', 'after_drop')
_DEFAULT_CONNECT_LISTENERS = (
    ('sqlalchemy.engine.create', 'create_engine.<locals>.on_connect'),
    ('sqlalchemy.util.langhelpers', 'only_once.<locals>.go'),
)


def _engine():
    return create_engine('sqlite:///:memory:',
                         connect_args={'check_same_thread': False},
                         poolclass=StaticPool)


def _schema_objects(metadata):
    yield metadata
    for table in metadata.tables.values():
        yield table
        yield from table.columns
        yield from table.constraints
        yield from table.indexes


def _builtin_enum_noop(listener, dialect):
    # SQLAlchemy registers SchemaType hooks for Enum even on SQLite. Those
    # hooks only dispatch to a *different* SchemaType implementation; for an
    # exact Enum mapped to exact Enum they do nothing. Reject subclasses and
    # patched hooks rather than exempting listeners by their module name.
    if type(listener) is not portable_instancemethod:
        return False
    target = listener.target
    expected = _ENUM_HOOKS.get(listener.name)
    return (
        type(target) is Enum
        and expected is not None
        and getattr(getattr(target, listener.name), '__func__', None) is expected
        and getattr(target._is_impl_for_variant, '__func__', None) is _ENUM_VARIANT_CHECK
        and getattr(target.dialect_impl, '__func__', None) is _ENUM_DIALECT_IMPL
        and type(target.dialect_impl(dialect)) is Enum
    )


def _bypass_reason(metadata, engine):
    for obj in _schema_objects(metadata):
        if getattr(obj, '_ddl_if', None) is not None:
            return 'conditional DDL'
        dispatch = getattr(obj, 'dispatch', None)
        if dispatch is not None and any(
            not _builtin_enum_noop(listener, engine.dialect)
            for name in _DDL_EVENTS for listener in getattr(dispatch, name, ())
        ):
            return 'schema event listener'
    for obj, label in ((engine, 'engine'), (engine.dialect, 'dialect'), (engine.pool, 'pool')):
        for name in obj.dispatch._event_names:
            listeners = list(getattr(obj.dispatch, name))
            if obj is engine.pool and name == 'connect':
                identities = tuple((listener.__module__, listener.__qualname__) for listener in listeners)
                if identities == _DEFAULT_CONNECT_LISTENERS:
                    continue
            if listeners:
                return f'{label} event listener'
    return None


def _fingerprint(metadata, dialect):
    """Recompile every schema, including constraints/defaults/index predicates.

    Object identity additionally detects equivalent replacement objects and
    ensures separately constructed metadata never shares a template implicitly.
    """
    parts = [str(id(obj)) for obj in _schema_objects(metadata)]
    for table in sorted(metadata.tables.values(), key=lambda item: item.key):
        parts.append(str(CreateTable(table).compile(dialect=dialect)))
        parts.extend(sorted(str(CreateIndex(index).compile(dialect=dialect)) for index in table.indexes))
    return hashlib.sha256('\0'.join(parts).encode()).hexdigest()


class SQLiteTemplate:
    def __init__(self):
        self._template = None
        self._key = None
        self._lock = RLock()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        with self._lock:
            if self._template is not None:
                self._template.dispose()
                self._template = None
                self._key = None

    @staticmethod
    def _backup(source, destination):
        with source.connect() as source_conn, destination.connect() as dest_conn:
            source_conn.connection.driver_connection.backup(dest_conn.connection.driver_connection)

    @contextmanager
    def database(self, metadata):
        engine = _engine()
        reason = None
        initialized = False
        try:
            with self._lock:
                reason = _bypass_reason(metadata, engine)
                if reason is not None:
                    logger.info('sqlite template bypass: %s', reason)
                    # Preserve the original fixture event and DDL semantics.
                    metadata.drop_all(bind=engine)
                    metadata.create_all(bind=engine)
                else:
                    key = _fingerprint(metadata, engine.dialect)
                    if key != self._key:
                        self.close()
                        template = _engine()
                        try:
                            metadata.create_all(bind=template)
                        except BaseException:
                            template.dispose()
                            raise
                        self._template = template
                        self._key = key
                    self._backup(self._template, engine)
                initialized = True
            yield engine
        finally:
            try:
                teardown_reason = reason or _bypass_reason(metadata, engine)
                if teardown_reason is not None and initialized:
                    if reason is None:
                        logger.info('sqlite template bypass: %s', teardown_reason)
                    metadata.drop_all(bind=engine)
            finally:
                engine.dispose()
