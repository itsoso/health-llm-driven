#!/usr/bin/env python3
"""Apply new managed migrations before restarting services."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main() -> int:
    from app.database import engine
    from app.services.managed_migrations import apply_managed_migrations, describe_migrations

    migrations_dir = ROOT / "migrations" / "managed"
    result = apply_managed_migrations(engine, migrations_dir)
    print(f"managed migrations applied: {describe_migrations(result.applied)}")
    print(f"managed migrations skipped: {describe_migrations(result.skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
