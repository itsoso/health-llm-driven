"""One-shot, fail-closed repair for legacy rows violating runtime null contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class RepairCounts:
    checkin_values: int
    template_owners: int
    orphan_templates: int
    progress_dates: int
    goal_titles: int


EXPECTED = RepairCounts(31, 12, 6, 4, 8)


def classify_template_rows(
    rows: Sequence[Mapping[str, object]],
) -> tuple[list[Mapping[str, object]], list[Mapping[str, object]]]:
    """Split null-owner templates into uniquely-derived owners and true orphans."""
    owned = [row for row in rows if int(row["owner_count"]) == 1]
    orphaned = [row for row in rows if int(row["record_count"]) == 0]
    ambiguous = [
        row
        for row in rows
        if int(row["owner_count"]) != 1 and int(row["record_count"]) != 0
    ]
    if ambiguous:
        raise RuntimeError("ambiguous checkin template ownership")
    return owned, orphaned


def _expect_rowcount(result: object, expected: int, operation: str) -> None:
    actual = getattr(result, "rowcount", None)
    if actual != expected:
        raise RuntimeError(
            f"unexpected affected rows for {operation}: expected={expected}, actual={actual}"
        )


def repair_runtime_null_contract(session: Session, *, apply: bool) -> RepairCounts:
    """Repair only the audited legacy population; otherwise fail and roll back."""
    session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    for table in ("checkin_records", "checkin_templates", "goal_progress", "goals"):
        session.execute(text(f"LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE"))

    template_rows = (
        session.execute(
            text(
                """
            SELECT t.id, count(DISTINCT r.user_id) AS owner_count,
                   min(r.user_id) AS owner_id, count(r.id) AS record_count
            FROM checkin_templates t
            LEFT JOIN checkin_records r ON r.template_id = t.id
            WHERE t.user_id IS NULL
            GROUP BY t.id
            """
            )
        )
        .mappings()
        .all()
    )
    owned, orphaned = classify_template_rows(template_rows)

    null_totals = (
        session.execute(
            text(
                """
            SELECT
              (SELECT count(*) FROM checkin_records WHERE value IS NULL) AS values_total,
              (SELECT count(*) FROM checkin_records r
                 JOIN checkin_templates t ON t.id = r.template_id
                WHERE r.value IS NULL AND t.default_target IS NOT NULL) AS values_derivable,
              (SELECT count(*) FROM goal_progress WHERE progress_date IS NULL) AS dates_total,
              (SELECT count(*) FROM goal_progress
                WHERE progress_date IS NULL AND created_at IS NOT NULL) AS dates_derivable,
              (SELECT count(*) FROM goals WHERE title IS NULL) AS titles_total,
              (SELECT count(*) FROM goals WHERE title IS NULL
                AND description IS NOT NULL AND length(btrim(description)) > 0) AS titles_derivable
            """
            )
        )
        .mappings()
        .one()
    )
    if any(
        int(null_totals[total]) != int(null_totals[derivable])
        for total, derivable in (
            ("values_total", "values_derivable"),
            ("dates_total", "dates_derivable"),
            ("titles_total", "titles_derivable"),
        )
    ):
        raise RuntimeError("runtime null population contains non-derivable rows")
    counts = RepairCounts(
        checkin_values=int(null_totals["values_total"]),
        template_owners=len(owned),
        orphan_templates=len(orphaned),
        progress_dates=int(null_totals["dates_total"]),
        goal_titles=int(null_totals["titles_total"]),
    )
    if counts != EXPECTED:
        raise RuntimeError(
            f"repair population changed: expected={EXPECTED}, actual={counts}"
        )

    if not apply:
        session.rollback()
        return counts

    _expect_rowcount(
        session.execute(
            text(
                """
            UPDATE checkin_templates t
            SET user_id = owners.user_id
            FROM (
                SELECT template_id, min(user_id) AS user_id
                FROM checkin_records
                WHERE user_id IS NOT NULL
                GROUP BY template_id
                HAVING count(DISTINCT user_id) = 1
            ) owners
            WHERE t.id = owners.template_id AND t.user_id IS NULL
            """
            )
        ),
        counts.template_owners,
        "derive template owners",
    )
    _expect_rowcount(
        session.execute(
            text(
                """
            UPDATE checkin_records r
            SET value = t.default_target,
                target = COALESCE(r.target, t.default_target),
                completion_rate = COALESCE(r.completion_rate, 100)
            FROM checkin_templates t
            WHERE r.template_id = t.id AND r.value IS NULL
              AND t.default_target IS NOT NULL
            """
            )
        ),
        counts.checkin_values,
        "derive checkin values",
    )
    _expect_rowcount(
        session.execute(
            text(
                """
            UPDATE goal_progress
            SET progress_date = (created_at AT TIME ZONE 'Asia/Shanghai')::date
            WHERE progress_date IS NULL AND created_at IS NOT NULL
            """
            )
        ),
        counts.progress_dates,
        "derive progress dates",
    )
    _expect_rowcount(
        session.execute(
            text(
                """
            UPDATE goals SET title = description
            WHERE title IS NULL AND description IS NOT NULL
              AND length(btrim(description)) > 0
            """
            )
        ),
        counts.goal_titles,
        "derive goal titles",
    )
    _expect_rowcount(
        session.execute(
            text(
                """
            DELETE FROM checkin_templates t
            WHERE t.user_id IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM checkin_records r WHERE r.template_id = t.id
              )
            """
            )
        ),
        counts.orphan_templates,
        "delete orphan templates",
    )

    remaining = session.execute(
        text(
            """
            SELECT
              (SELECT count(*) FROM checkin_records WHERE value IS NULL) +
              (SELECT count(*) FROM checkin_templates WHERE user_id IS NULL) +
              (SELECT count(*) FROM goal_progress WHERE progress_date IS NULL) +
              (SELECT count(*) FROM goals WHERE title IS NULL)
            """
        )
    ).scalar_one()
    if remaining != 0:
        raise RuntimeError(f"repair incomplete: remaining_nulls={remaining}")
    session.commit()
    return counts
