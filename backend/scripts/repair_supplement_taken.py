#!/usr/bin/env python
"""Audit or apply the frozen September 2026 supplement ``taken`` repair.

Default mode is a dry run that verifies the audited population and rolls back.
``--apply`` writes; run it only with explicit owner approval.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import SessionLocal
from app.services.supplement_taken_repair import RECORD_IDS, USER_ID, repair_supplement_taken
from app.twin.cache import invalidate_twin


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="persist the repair")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        rows = repair_supplement_taken(session, apply=args.apply)
    finally:
        session.close()
    if args.apply:
        invalidate_twin(USER_ID)
    # Audit evidence for the dossier: exactly these rows, and the state they were flipped from.
    print("SUPPLEMENT_TAKEN_REPAIR_OK " + json.dumps({
        "apply": args.apply,
        "user_id": USER_ID,
        "rows": rows,
        "record_ids": list(RECORD_IDS),
        "prior_state": {"taken": False, "taken_time": None},
    }))


if __name__ == "__main__":
    main()
