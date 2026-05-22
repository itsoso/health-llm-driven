#!/usr/bin/env python3
"""Import a WeGene/23andMe-style raw genotype TXT file for one user.

The script stores structured variants and provenance only. It does not persist
the original raw TXT content.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session  # noqa: E402

from app.api.genetic_data import (  # noqa: E402
    KNOWN_SNPS,
    _build_import_coverage,
    _derive_apoe_epsilon,
    _known_variant_payload,
    _normalize_rsid,
    _utcnow,
)
from app.database import SessionLocal  # noqa: E402
from app.models.genetic_data import GeneticImportJob, GeneticProfile, GeneticVariant  # noqa: E402
from app.models.user import User  # noqa: E402


PARSER_VERSION = "genetic-import-v2-script"


def _read_text_file(file_path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return file_path.read_text(encoding="utf-8", errors="ignore")


def _parse_raw_genotypes(txt_content: str) -> tuple[Dict[str, str], int, int]:
    raw_by_rsid: Dict[str, str] = {}
    raw_record_count = 0
    duplicate_count = 0

    for line in txt_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        rsid = _normalize_rsid(parts[0])
        genotype = parts[3].strip()
        if not rsid or genotype == "--":
            continue
        raw_record_count += 1
        if rsid in raw_by_rsid:
            duplicate_count += 1
            continue
        raw_by_rsid[rsid] = genotype

    return raw_by_rsid, raw_record_count, duplicate_count


def _payload_for_known_rsid(rsid: str, genotype: str, raw_by_rsid: Dict[str, str]) -> Optional[Dict[str, Any]]:
    snp = KNOWN_SNPS[rsid]
    if rsid != "rs429358":
        return _known_variant_payload(rsid, genotype, snp)

    apoe = _derive_apoe_epsilon(raw_by_rsid)
    if apoe is None:
        return None
    return {
        "rsid": rsid,
        "category": snp["category"],
        "gene_name": snp["gene"],
        "variant_name": "APOE ε2/ε3/ε4 双位点分型",
        "description": "APOE ε 型需要 rs429358 + rs7412 共同判定；单个位点不作最终风险结论。",
        "mapping_source": "apoe_pair",
        **apoe,
    }


def _run_side_effects(db: Session, user_id: int, profile_id: int) -> None:
    try:
        from app.services.memory_extractor import bulk_extract_genes_for_profile

        bulk_extract_genes_for_profile(db, user_id, profile_id)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()

    try:
        from app.twin.cache import invalidate_twin

        invalidate_twin(user_id)
    except Exception:  # noqa: BLE001
        pass


def import_txt_file(
    db: Session,
    *,
    user_id: int,
    file_path: str | Path,
    provider: str,
    test_date: date,
    notes: Optional[str] = None,
    report_id: Optional[str] = None,
    run_side_effects: bool = False,
) -> Dict[str, Any]:
    """Import one raw genotype TXT file into structured genetic tables."""
    path = Path(file_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"TXT file not found: {path}")

    user = db.get(User, user_id)
    if user is None:
        raise ValueError(f"user_id={user_id} does not exist")

    txt_content = _read_text_file(path)
    raw_hash = hashlib.sha256(txt_content.encode("utf-8", errors="ignore")).hexdigest()
    raw_by_rsid, raw_record_count, duplicate_count = _parse_raw_genotypes(txt_content)

    profile = GeneticProfile(
        user_id=user_id,
        test_provider=provider,
        test_date=test_date,
        report_id=report_id,
        notes=notes or "TXT 原始数据解析",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    import_job = GeneticImportJob(
        user_id=user_id,
        profile_id=profile.id,
        source_type="txt",
        provider=provider,
        status="processing",
        parser_version=PARSER_VERSION,
        raw_file_hash=raw_hash,
        raw_record_count=raw_record_count,
        known_total=len(KNOWN_SNPS),
        duplicate_count=duplicate_count,
        started_at=_utcnow(),
    )
    db.add(import_job)
    db.commit()
    db.refresh(import_job)

    matched_count = 0
    matched_rsids: set[str] = set()
    unmapped_count = 0

    try:
        for rsid, genotype in raw_by_rsid.items():
            if rsid not in KNOWN_SNPS:
                continue
            payload = _payload_for_known_rsid(rsid, genotype, raw_by_rsid)
            if payload is None:
                unmapped_count += 1
                continue

            db.add(
                GeneticVariant(
                    user_id=user_id,
                    profile_id=profile.id,
                    rsid=payload["rsid"],
                    category=payload["category"],
                    gene_name=payload["gene_name"],
                    variant_name=payload["variant_name"],
                    genotype=payload["genotype"],
                    raw_genotype=payload["raw_genotype"],
                    result_label=payload["result_label"],
                    risk_level=payload["risk_level"],
                    description=payload["description"],
                    health_implications=payload.get("health_implications"),
                    mapping_source=payload.get("mapping_source", "known_snp"),
                    evidence_level=payload.get("evidence_level", "screening"),
                )
            )
            matched_rsids.add(rsid)
            matched_count += 1

        coverage = _build_import_coverage(matched_rsids, set(raw_by_rsid.keys()))
        profile.notes = f"TXT 解析完成，匹配 {matched_count} 个健康位点"
        import_job.status = "done"
        import_job.matched_count = matched_count
        import_job.unknown_count = max(len(set(raw_by_rsid.keys()) - set(KNOWN_SNPS.keys())), 0)
        import_job.unmapped_count = unmapped_count
        import_job.missing_count = coverage["missing"]
        import_job.coverage_summary = coverage
        import_job.finished_at = _utcnow()
        db.commit()
    except Exception as exc:
        db.rollback()
        import_job = db.get(GeneticImportJob, import_job.id)
        if import_job is not None:
            import_job.status = "failed"
            import_job.error_message = str(exc)[:2000]
            import_job.finished_at = _utcnow()
            db.commit()
        raise

    if run_side_effects:
        _run_side_effects(db, user_id, profile.id)

    return {
        "profile_id": profile.id,
        "import_job_id": import_job.id,
        "status": import_job.status,
        "provider": provider,
        "test_date": test_date.isoformat(),
        "raw_record_count": raw_record_count,
        "known_total": len(KNOWN_SNPS),
        "matched_count": matched_count,
        "duplicate_count": duplicate_count,
        "unknown_count": import_job.unknown_count or 0,
        "unmapped_count": unmapped_count,
        "missing_count": import_job.missing_count or 0,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import raw genetic TXT data for a user.")
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--file", required=True, help="Path to WeGene/23andMe-style TXT file")
    parser.add_argument("--provider", default="WeGene")
    parser.add_argument("--test-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--notes")
    parser.add_argument("--report-id")
    parser.add_argument("--skip-side-effects", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    db = SessionLocal()
    try:
        result = import_txt_file(
            db,
            user_id=args.user_id,
            file_path=args.file,
            provider=args.provider,
            test_date=date.fromisoformat(args.test_date),
            notes=args.notes,
            report_id=args.report_id,
            run_side_effects=not args.skip_side_effects,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"导入失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
