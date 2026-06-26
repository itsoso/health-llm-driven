#!/usr/bin/env python3
"""Export a real-data fixture for the Reva Mobile design prototype.

Consolidates a user's production data into a single JSON the "Claude Design"
session can paste in to replace hard-coded sample values (张子衡 / 就绪度86 / …).
Runs against whatever DATABASE_URL the env points at — run it on prod (or via
ssh) to get real values, since local SQLite is empty for most accounts.

Usage (prod):
    ssh root@<prod> "cd /opt/health-app/backend && source venv/bin/activate && \
        python3 scripts/export_design_fixture.py --user 3" > design/fixtures/user3.json

Output is a single JSON document on stdout:
    { _meta, persona, active_medications, supplements, health_problems,
      headline (fake→real anchor values), twin (full 14-partition snapshot) }

The fixture contains real health data (Tier-5). Treat the output file as
sensitive; do not commit fixtures with real PII into the repo.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.twin.builder import build_twin  # noqa: E402


def _first(db, sql: str, **params):
    try:
        row = db.execute(text(sql), params).mappings().first()
        return dict(row) if row else None
    except Exception:
        return None


def _all(db, sql: str, **params):
    try:
        return [dict(r) for r in db.execute(text(sql), params).mappings().all()]
    except Exception:
        return []


def _age_from_birth(birth) -> int | None:
    if not birth:
        return None
    try:
        b = birth if isinstance(birth, date) else date.fromisoformat(str(birth)[:10])
        today = date.today()
        return today.year - b.year - ((today.month, today.day) < (b.month, b.day))
    except Exception:
        return None


def _headline(twin: dict, persona: dict, active_meds: list) -> dict:
    """The anchor values the prototype hard-codes — mapped to their real source."""
    p = twin.get("physiological", {})
    l = twin.get("labs", {})
    env = twin.get("environment", {})
    ch = twin.get("chronic", {})
    med = twin.get("medication", {})
    return {
        "training_readiness": f"{p.get('training_readiness_score')} ({p.get('training_readiness_level')})",
        "resting_hr": p.get("resting_hr"),
        "hrv": p.get("hrv_latest"),
        "sleep_score": p.get("sleep_score_latest"),
        "sleep_hours": p.get("sleep_duration_h_latest"),
        "body_battery": p.get("body_battery_current"),
        "stress": p.get("stress_level_current"),
        "steps_today": p.get("steps_today"),
        "spo2_avg": p.get("spo2_avg"),
        "vo2max": p.get("vo2max_running"),
        "ldl": l.get("ldl"),
        "total_cholesterol": l.get("total_cholesterol"),
        "hdl": l.get("hdl"),
        "triglycerides": l.get("triglycerides"),
        "fasting_glucose": l.get("blood_glucose"),
        "hba1c": l.get("hba1c"),
        "blood_pressure": f"{l.get('blood_pressure_systolic')}/{l.get('blood_pressure_diastolic')}",
        "uric_acid": l.get("uric_acid"),
        "egfr": l.get("egfr"),
        "phenotypic_age": l.get("phenotypic_age"),
        "last_exam_date": l.get("last_exam_date"),
        "aqi": env.get("aqi"),
        "pm25": env.get("pm25"),
        "temperature_c": env.get("temperature_c"),
        "humidity_pct": env.get("humidity_pct"),
        "city": env.get("city") or persona.get("city"),
        "active_conditions": ch.get("active_conditions"),
        "medication_adherence_7d_pct": med.get("adherence_7d_pct"),
        "active_medication_count": len(active_meds),
    }


def export(user_id: int) -> dict:
    db = SessionLocal()
    try:
        twin = build_twin(db, user_id, use_cache=False).model_dump(mode="json")

        user = _first(db, "SELECT id, username, email FROM users WHERE id=:u", u=user_id) or {}
        prof = _first(
            db,
            "SELECT gender, birth_date, height_cm, city, timezone, occupation "
            "FROM user_profiles WHERE user_id=:u",
            u=user_id,
        ) or {}
        persona = {
            "username": user.get("username"),
            "gender": prof.get("gender"),
            "birth_date": str(prof.get("birth_date")) if prof.get("birth_date") else None,
            "age": _age_from_birth(prof.get("birth_date")),
            "height_cm": prof.get("height_cm"),
            "city": prof.get("city"),
            "timezone": prof.get("timezone"),
            "occupation": prof.get("occupation"),
        }

        meds = _all(
            db,
            "SELECT name, dosage, frequency, is_active FROM medications "
            "WHERE user_id=:u ORDER BY is_active DESC",
            u=user_id,
        )
        active_meds = [m for m in meds if m.get("is_active")]
        supplements = _all(db, "SELECT name, dosage FROM supplements WHERE user_id=:u", u=user_id)
        problems = _all(
            db,
            "SELECT title, severity, status FROM health_problems WHERE user_id=:u",
            u=user_id,
        )

        return {
            "_meta": {
                "source": "production DB (run via ssh on prod)",
                "user_id": user_id,
                "generated_at": twin.get("meta", {}).get("generated_at"),
                "note": "真实数据。Reva Mobile 设计原型 data-layer 的真实来源,字段以 backend twin schema 为准(14 分区)。",
            },
            "persona": persona,
            "active_medications": active_meds,
            "supplements": supplements,
            "health_problems": problems,
            "headline": _headline(twin, persona, active_meds),
            "twin": twin,
        }
    finally:
        db.close()


def main():
    ap = argparse.ArgumentParser(description="Export real-data design fixture for a user.")
    ap.add_argument("--user", type=int, required=True, help="user_id to export")
    args = ap.parse_args()
    sys.stdout.write(json.dumps(export(args.user), ensure_ascii=False, indent=2, default=str))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
