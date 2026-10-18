"""Serialize medication reminder admission while PushService commits its receipt."""
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session

# Two-key PostgreSQL advisory namespace, distinct from application row IDs.
_MEDICATION_DISPATCH_NAMESPACE = 1835361380


@contextmanager
def medication_dispatch_lock(db: Session, user_id: int):
    engine = db.get_bind()
    if engine.dialect.name != 'postgresql':
        raise RuntimeError('medication_dispatch_requires_postgresql')
    # A dedicated physical connection retains this session lock across the
    # PushService pending/terminal commits. Transaction locks would release early.
    with engine.connect() as connection:
        params = {'namespace': _MEDICATION_DISPATCH_NAMESPACE, 'owner': user_id}
        try:
            acquired = connection.scalar(text('SELECT pg_try_advisory_lock(:namespace, :owner)'), params)
            connection.commit()
        except BaseException:
            connection.invalidate()
            raise
        try:
            yield bool(acquired)
        finally:
            if acquired:
                try:
                    released = connection.scalar(text('SELECT pg_advisory_unlock(:namespace, :owner)'), params)
                    connection.commit()
                    if not released:
                        raise RuntimeError('medication_dispatch_lock_not_released')
                except BaseException:
                    # Never return a possibly locked session to the pool.
                    connection.invalidate()
                    raise
