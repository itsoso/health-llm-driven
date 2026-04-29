#!/usr/bin/env python3
"""
Memory / KG Backfill — 把现有存量数据一次性灌进 Memory/KG

背景: Sprint 5 (2026-04-28) ship 之后 2 天, memory_facts 只有 1 条 (单元测试 fixture),
health_entities 3 条 (fixture), entity_relations 2 条 (fixture). 原因:
  1. orchestrator 的 extract hook 虽然挂了, 但 orchestrator 7 天只跑 2 次 (流量太小)
  2. medications / medical_indicators / genetic_variants 等主力数据源从未被 extractor 触碰
  3. briefing_task (每天写 SOAP) 的 extractor 没写

本脚本:
  - 扫所有 user (或 --user)
  - 对每种数据源调对应 extractor
  - 报告写入数量; 失败不中断下一个

使用:
  python scripts/memory_backfill.py                  # 全量, dry-run
  python scripts/memory_backfill.py --user 3         # 单用户
  python scripts/memory_backfill.py --user 3 --commit  # 真写入
  python scripts/memory_backfill.py --remote --user 3 --commit  # SSH 跑线上
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent
sys.path.insert(0, str(BACKEND_ROOT))


def _session():
    from app.database import SessionLocal
    return SessionLocal()


def backfill_user(db, user_id: int, commit: bool) -> dict:
    """返回 {source_type: count_written} 的统计."""
    from app.services.memory_extractor import (
        extract_from_medical_exam_item,
        extract_kg_from_lab,
        extract_kg_from_medication,
        extract_kg_from_gene_variant,
        extract_from_directive,
        extract_from_action_card_outcome,
        extract_from_briefing_entry,
    )
    from app.models.medication import Medication
    from app.models.family_health import MedicalIndicator
    from app.models.genetic_data import GeneticVariant
    from app.models.action_card import ActionCard
    from app.models.clinical_journal import ClinicalJournalEntry

    stats = {
        "medications": 0,
        "medical_indicators_fact": 0,
        "medical_indicators_kg": 0,
        "gene_variants": 0,
        "gene_variants_skipped": 0,
        "directives": 0,
        "action_cards_graded": 0,
        "journal_entries": 0,
    }

    # 1. Medications → KG
    meds = db.query(Medication).filter(
        Medication.user_id == user_id,
        Medication.is_active.is_(True),
    ).all()
    for med in meds:
        try:
            eid = extract_kg_from_medication(db, user_id, med)
            if eid:
                stats["medications"] += 1
        except Exception as e:
            print(f"  [skip] medication id={med.id}: {e}")

    # 2. MedicalIndicator (abnormal) → fact + KG
    labs = db.query(MedicalIndicator).filter(
        MedicalIndicator.user_id == user_id,
        MedicalIndicator.is_abnormal.is_(True),
    ).all()
    for lab in labs:
        try:
            fid = extract_from_medical_exam_item(db, user_id, lab)
            if fid:
                stats["medical_indicators_fact"] += 1
            eid = extract_kg_from_lab(db, user_id, lab)
            if eid:
                stats["medical_indicators_kg"] += 1
        except Exception as e:
            print(f"  [skip] lab id={lab.id}: {e}")

    # 3. GeneticVariant → KG (only clinically meaningful)
    genes = db.query(GeneticVariant).filter(
        GeneticVariant.user_id == user_id,
    ).all()
    for g in genes:
        try:
            eid = extract_kg_from_gene_variant(db, user_id, g)
            if eid:
                stats["gene_variants"] += 1
            else:
                stats["gene_variants_skipped"] += 1
        except Exception as e:
            print(f"  [skip] gene id={g.id}: {e}")

    # 4. UserDirectives (if model exists)
    try:
        from app.models.user_directive import UserDirective
        directives = db.query(UserDirective).filter(
            UserDirective.user_id == user_id,
        ).all()
        for d in directives:
            try:
                fid = extract_from_directive(db, d)
                if fid:
                    stats["directives"] += 1
            except Exception as e:
                print(f"  [skip] directive id={d.id}: {e}")
    except ImportError:
        pass

    # 5. ActionCards (graded) → procedural
    cards = db.query(ActionCard).filter(
        ActionCard.user_id == user_id,
        ActionCard.graded_at.isnot(None),
    ).all()
    for c in cards:
        try:
            fid = extract_from_action_card_outcome(db, c)
            if fid:
                stats["action_cards_graded"] += 1
        except Exception as e:
            print(f"  [skip] action_card id={c.id}: {e}")

    # 6. Clinical Journal Entries (所有来源, 但重点是 briefing)
    entries = db.query(ClinicalJournalEntry).filter(
        ClinicalJournalEntry.user_id == user_id,
    ).all()
    for e in entries:
        try:
            fids = extract_from_briefing_entry(db, e)
            stats["journal_entries"] += len(fids)
        except Exception as ex:
            print(f"  [skip] journal_entry id={e.id}: {ex}")

    if commit:
        db.commit()
    else:
        db.rollback()

    return stats


def run_remote(user: int | None, commit: bool) -> int:
    parts = [
        "cd /opt/health-app/backend && source venv/bin/activate &&",
        "python scripts/memory_backfill.py",
    ]
    if user is not None:
        parts.append(f"--user {user}")
    if commit:
        parts.append("--commit")
    cmd = " ".join(parts)
    result = subprocess.run(["ssh", "root@39.98.206.178", cmd], text=True)
    return result.returncode


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--user", type=int, default=None)
    p.add_argument("--commit", action="store_true", help="真写入; 不加则 dry-run + rollback")
    p.add_argument("--remote", action="store_true")
    args = p.parse_args()

    if args.remote:
        sys.exit(run_remote(args.user, args.commit))

    db = _session()
    try:
        if args.user is not None:
            user_ids = [args.user]
        else:
            from app.models.user import User
            user_ids = [u.id for u in db.query(User).all()]

        mode = "COMMIT" if args.commit else "DRY-RUN (rollback)"
        print(f"\n📦 Memory/KG Backfill — {mode} — {len(user_ids)} 用户\n")

        total = {}
        for uid in user_ids:
            # 每个 user 单独 session 避免互相影响
            u_db = _session()
            try:
                print(f"--- user_id={uid}")
                stats = backfill_user(u_db, uid, args.commit)
                for k, v in stats.items():
                    total[k] = total.get(k, 0) + v
                for k, v in stats.items():
                    if v:
                        print(f"    {k:<26} {v}")
            finally:
                u_db.close()

        print(f"\n✅ 汇总 ({mode}):")
        for k, v in sorted(total.items(), key=lambda kv: -kv[1]):
            print(f"  {k:<26} {v}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
