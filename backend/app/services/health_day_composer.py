"""Dormant Health Day composer seam.

Task 1 exposes only the behavior-free contracts leaf. Composition is added by a
later task after digest-bound source loading exists.
"""

from __future__ import annotations

from app.services import health_day_shadow_contracts as contracts


__all__ = ("contracts",)
