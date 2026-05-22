from datetime import date

from app.models.genetic_data import GeneticImportJob, GeneticProfile, GeneticVariant
from app.models.user import User


def test_import_txt_file_creates_profile_job_and_curated_variants(db, tmp_path):
    from scripts.import_genetic_txt import import_txt_file

    user = User(
        username="genetic_import_user",
        email="genetic_import_user@example.com",
        hashed_password="hashed",
        name="Genetic Import User",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    txt_file = tmp_path / "wegene.txt"
    txt_file.write_text(
        "\n".join(
            [
                "# rsid\tchromosome\tposition\tgenotype",
                "rs1061235\t6\t29945884\tAA",
                "rs7454108\t6\t32605884\tCT",
                "rs121908763\t7\t117559593\tGG",
                "rs380390\t1\t196659237\tCC",
                "rs2230199\t19\t6718387\tCC",
                "rs137853280\t13\t51958376\tGG",
            ]
        ),
        encoding="utf-8",
    )

    result = import_txt_file(
        db,
        user_id=user.id,
        file_path=txt_file,
        provider="WeGene",
        test_date=date(2026, 5, 16),
        notes="script import test",
    )

    assert result["matched_count"] == 6
    assert result["raw_record_count"] == 6
    assert result["status"] == "done"

    profile = db.query(GeneticProfile).filter_by(user_id=user.id).one()
    assert profile.test_provider == "WeGene"
    assert profile.notes == "TXT 解析完成，匹配 6 个健康位点"

    job = db.query(GeneticImportJob).filter_by(user_id=user.id, profile_id=profile.id).one()
    assert job.source_type == "txt"
    assert job.raw_file_hash
    assert job.known_total >= 69
    assert job.matched_count == 6
    assert job.status == "done"

    variants = {
        variant.rsid: variant
        for variant in db.query(GeneticVariant).filter_by(user_id=user.id, profile_id=profile.id).all()
    }
    assert variants["rs1061235"].gene_name == "HLA-A*31:01"
    assert variants["rs1061235"].evidence_level == "requires_confirmation"
    assert variants["rs121908763"].gene_name == "CFTR"
    assert variants["rs137853280"].gene_name == "ATP7B"
