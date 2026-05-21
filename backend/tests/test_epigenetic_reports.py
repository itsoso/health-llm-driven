from datetime import date

from tests.conftest import create_authenticated_user


def test_epigenetic_report_model_stores_vendor_clock_and_raw_summary(db):
    from app.models.epigenetic_report import EpigeneticReport

    user, _ = create_authenticated_user(db)
    report = EpigeneticReport(
        user_id=user.id,
        vendor="TruDiagnostic",
        sample_date=date(2026, 5, 1),
        clock_type="DunedinPACE",
        biological_age=41.3,
        pace_of_aging=1.08,
        confidence="low",
        raw_summary={"pace_percentile": 68, "notes": ["commercial epigenetic clock"]},
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    assert report.id is not None
    assert report.user_id == user.id
    assert report.vendor == "TruDiagnostic"
    assert report.sample_date == date(2026, 5, 1)
    assert report.clock_type == "DunedinPACE"
    assert report.biological_age == 41.3
    assert report.pace_of_aging == 1.08
    assert report.confidence == "low"
    assert report.raw_summary["pace_percentile"] == 68


def test_epigenetic_report_queries_are_scoped_by_user(db):
    from app.models.epigenetic_report import EpigeneticReport
    from app.services.epigenetic_report_service import list_epigenetic_reports

    user_a, _ = create_authenticated_user(db)
    user_b, _ = create_authenticated_user(db)
    db.add_all(
        [
            EpigeneticReport(
                user_id=user_a.id,
                vendor="AgingAI",
                sample_date=date(2026, 5, 1),
                clock_type="pace",
                raw_summary={"owner": "a"},
            ),
            EpigeneticReport(
                user_id=user_b.id,
                vendor="AgingAI",
                sample_date=date(2026, 5, 2),
                clock_type="pace",
                raw_summary={"owner": "b"},
            ),
        ]
    )
    db.commit()

    rows = list_epigenetic_reports(db, user_a.id)

    assert len(rows) == 1
    assert rows[0]["user_id"] == user_a.id
    assert rows[0]["raw_summary"] == {"owner": "a"}


def test_epigenetic_report_summary_defaults_to_experimental_low_boundary(db):
    from app.models.epigenetic_report import EpigeneticReport
    from app.services.epigenetic_report_service import epigenetic_report_summary

    user, _ = create_authenticated_user(db)
    report = EpigeneticReport(
        user_id=user.id,
        vendor="AgingAI",
        sample_date=date(2026, 5, 1),
        clock_type="pace",
        biological_age=39.5,
        pace_of_aging=0.97,
        raw_summary={"headline": "pace improved"},
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    summary = epigenetic_report_summary(report)

    assert summary["evidence_tier"] == "experimental"
    assert summary["confidence"] == "low"
    assert summary["claim_boundary"].startswith("表观遗传商业报告属于实验性健康趋势参考")
    assert "不替代医生诊断" in summary["claim_boundary"]
    assert summary["biological_age"] == 39.5
    assert summary["pace_of_aging"] == 0.97


def test_latest_epigenetic_state_maps_report_into_twin_boundary(db):
    from app.models.epigenetic_report import EpigeneticReport
    from app.services.epigenetic_report_service import latest_epigenetic_state

    user, _ = create_authenticated_user(db)
    user.birth_date = date(1990, 1, 1)
    db.add_all(
        [
            EpigeneticReport(
                user_id=user.id,
                vendor="OlderClock",
                sample_date=date(2026, 1, 1),
                clock_type="PACE",
                biological_age=39.1,
                pace_of_aging=1.01,
            ),
            EpigeneticReport(
                user_id=user.id,
                vendor="TruDiagnostic",
                sample_date=date(2026, 5, 1),
                clock_type="DunedinPACE",
                biological_age=41.2,
                pace_of_aging=1.11,
            ),
        ]
    )
    db.commit()

    state = latest_epigenetic_state(db, user.id)

    assert state.has_methylation_report is True
    assert state.status == "present"
    assert state.latest_test_date == "2026-05-01"
    assert state.vendor == "TruDiagnostic"
    assert state.clock_type == "DunedinPACE"
    assert state.biological_age == 41.2
    assert state.biological_age_delta_years == 4.9
    assert state.pace_of_aging == 1.11
    assert state.evidence_tier == "experimental"
    assert state.confidence == "low"
    assert "不能证明个体短期干预成效" in state.claim_boundary
