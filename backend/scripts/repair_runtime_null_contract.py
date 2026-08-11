#!/usr/bin/env python3
"""Audit or apply the frozen production runtime-null repair."""

from __future__ import annotations

import argparse

from app.database import SessionLocal
from app.services.runtime_null_contract_repair import repair_runtime_null_contract


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    session = SessionLocal()
    try:
        counts = repair_runtime_null_contract(session, apply=args.apply)
        print(f"RUNTIME_NULL_REPAIR_OK apply={args.apply} counts={counts}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
