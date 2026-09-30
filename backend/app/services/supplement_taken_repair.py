"""One-shot, fail-closed repair for September 2026 intakes stored as ``taken=false``.

Audited read-only on production (2026-09-30): an external API client created
these rows via ``POST /supplements/records`` without ``taken``; the schema
default stored "not taken" although every note describes the intake, and no
first-party agent operation owns them. The population is frozen by id and
re-verified against the evidence predicate before any write.

The unmapped legacy ``taken_count`` column is deliberately not evidence: it is
the server default 1 on every row, including legitimate un-checks.

An applied run flips exactly ``RECORD_IDS`` (rowcount is enforced) from
``taken=false, taken_time=NULL``; the script prints that as JSON for the
dossier. Rollback restores the same rows; the table has no ``updated_at``, so
first confirm none of them was re-edited after the repair::

    UPDATE supplement_records SET taken = false
    WHERE user_id = 3 AND id IN (<RECORD_IDS>) AND taken = true
      AND taken_time IS NULL AND record_date BETWEEN '2026-09-01' AND '2026-09-30';
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

USER_ID = 3
RECORD_IDS = (
    1088, 1089, 1090, 1091, 1092, 1093, 1094, 1098,
    1099, 1100, 1101, 1102, 1103, 1104, 1105, 1106,
)

_EVIDENCE = """
    user_id = :user_id AND taken = false AND taken_time IS NULL
    AND notes IS NOT NULL AND trim(notes) <> ''
    AND record_date BETWEEN :first_day AND :last_day
"""
_PARAMS = {"user_id": USER_ID, "first_day": date(2026, 9, 1), "last_day": date(2026, 9, 30)}


def repair_supplement_taken(session: Session, *, apply: bool) -> int:
    """Mark only the audited rows taken; any population drift raises and rolls back."""
    if session.in_transaction():  # SERIALIZABLE must be the transaction's first statement
        raise RuntimeError("repair must run in its own transaction; commit or roll back first")
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
        # Never queue behind a long transaction while blocking every supplement write.
        session.execute(text("SET LOCAL lock_timeout = '5s'"))
        session.execute(text("LOCK TABLE supplement_records IN SHARE ROW EXCLUSIVE MODE"))

    matched = sorted(
        session.execute(text(f"SELECT id FROM supplement_records WHERE {_EVIDENCE}"), _PARAMS).scalars()
    )
    if matched != sorted(RECORD_IDS):
        session.rollback()
        raise RuntimeError(f"repair population changed: expected={list(RECORD_IDS)}, actual={matched}")

    if not apply:
        session.rollback()
        return len(matched)

    result = session.execute(
        text(f"UPDATE supplement_records SET taken = true WHERE id IN :ids AND {_EVIDENCE}")
        .bindparams(bindparam("ids", expanding=True)),
        {**_PARAMS, "ids": list(RECORD_IDS)},
    )
    if result.rowcount != len(RECORD_IDS):
        session.rollback()
        raise RuntimeError(
            f"unexpected affected rows: expected={len(RECORD_IDS)}, actual={result.rowcount}"
        )
    session.commit()
    return len(RECORD_IDS)
