"""Withings token refresh that saves the rotated pair before anything else can fail.

Withings may rotate the refresh token on every refresh, which kills the old one. The new
pair is therefore committed right after the refresh succeeds, not at the end of the
request: a retry that fails afterwards must not leave a dead refresh token on the
credential (the weight / blood pressure / sleep webhooks would stop for good).

Concurrent refreshes of one credential (two webhooks for the same measurement) are
serialised per process; production runs a single uvicorn worker (deploy.sh enforces
`--workers 1`). A request that waited re-reads the credential and reuses the pair
another request already saved instead of spending the rotated-away refresh token.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models.device_credential import DeviceCredential

from .withings import WithingsHealthAdapter

logger = logging.getLogger(__name__)

DEFAULT_ACCESS_TOKEN_SECONDS = 10800  # Withings access tokens last 3 hours

_refresh_locks: Dict[Tuple[int, int], asyncio.Lock] = {}


class WithingsTokenStore:
    """Refreshes a credential's tokens and saves them immediately."""

    def __init__(self, db: Session, credential: DeviceCredential):
        self.db = db
        self.credential = credential

    async def refresh(self, adapter: WithingsHealthAdapter) -> bool:
        rejected_access_token = adapter.access_token
        # asyncio locks belong to one event loop; production has one, tests start several.
        key = (id(asyncio.get_running_loop()), self.credential.id)
        lock = _refresh_locks.setdefault(key, asyncio.Lock())
        async with lock:
            self.db.refresh(self.credential)
            stored_access_token = self.credential.get_access_token()
            if stored_access_token and stored_access_token != rejected_access_token:
                # Another request refreshed while this one waited.
                adapter.access_token = stored_access_token
                adapter._refresh_token = self.credential.get_refresh_token()
                return True

            if not await adapter.refresh_token():
                return False
            self._save(adapter)
            return True

    def _save(self, adapter: WithingsHealthAdapter) -> None:
        user_id = self.credential.user_id
        expires_in = adapter.token_expires_in or DEFAULT_ACCESS_TOKEN_SECONDS
        try:
            self.credential.set_oauth_tokens(
                access_token=adapter.access_token,
                refresh_token=adapter._refresh_token,
                expires_at=datetime.now() + timedelta(seconds=expires_in),
            )
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(
                "Withings refreshed tokens NOT persisted: user_id=%s error=%s",
                user_id, type(e).__name__,
            )
            raise
        logger.info("Withings refreshed tokens persisted: user_id=%s", user_id)


def build_withings_adapter(db: Session, credential: DeviceCredential) -> WithingsHealthAdapter:
    """Adapter for a stored credential whose token refreshes are saved as they happen."""
    return WithingsHealthAdapter(
        client_id=settings.withings_client_id,
        client_secret=settings.withings_client_secret,
        access_token=credential.get_access_token(),
        refresh_token=credential.get_refresh_token(),
        token_store=WithingsTokenStore(db, credential),
    )
