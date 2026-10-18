"""Serialize medication reminder admission while PushService commits its receipt."""
from contextlib import contextmanager
import hashlib

from sqlalchemy import text
from sqlalchemy.orm import Session



@contextmanager
def medication_dispatch_lock(db: Session, user_id: int, occurrence: str):
    engine = db.get_bind()
    if engine.dialect.name != 'postgresql':
        raise RuntimeError('medication_dispatch_requires_postgresql')
    # A dedicated physical connection retains this session lock across the
    # PushService pending/terminal commits. Transaction locks would release early.
    with engine.connect() as connection:
        key = int.from_bytes(hashlib.sha256(f'reva.medication.slot.v1:{user_id}:{occurrence}'.encode()).digest()[:8], 'big', signed=True)
        params = {'key': key}
        try:
            acquired = connection.scalar(text('SELECT pg_try_advisory_lock(:key)'), params)
            connection.commit()
        except BaseException:
            connection.invalidate()
            raise
        try:
            yield bool(acquired)
        finally:
            if acquired:
                try:
                    released = connection.scalar(text('SELECT pg_advisory_unlock(:key)'), params)
                    connection.commit()
                    if not released:
                        raise RuntimeError('medication_dispatch_lock_not_released')
                except BaseException:
                    # Never return a possibly locked session to the pool.
                    connection.invalidate()
                    raise
