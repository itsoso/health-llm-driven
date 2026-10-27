"""The additional exam table must use a bounded canonical migration profile."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_exam_addition_has_distinct_source_admission_and_receipt():
    text = (ROOT / 'deploy.sh').read_text()
    admission = text.split('verify_code_only_source_changes() {', 1)[1].split('daily_journey_release_command() {', 1)[0]
    assert 'EXAM_ATTEMPTS_ADDITIVE=0' in admission
    assert 'scripts/exam_attempts_release.py' in admission
    assert '"EXAM_ATTEMPTS_ADDITIVE"' in admission
    assert 'return 1' in admission
    loader = text.split("<<'DAILY_JOURNEY_LOADER'", 1)[1].split('\nDAILY_JOURNEY_LOADER', 1)[0]
    assert "if profile not in ('daily_journey_release.py', 'exam_attempts_release.py')" in loader
    assert "git('rev-parse',sha+':scripts/'+profile)" in loader
    preflight = text.split('daily_journey_release_preflight() {', 1)[1].split('\n}', 1)[0]
    assert 'prefix="EXAM_ATTEMPTS"' in preflight
    assert '${prefix}_PREFLIGHT_OK pending=1' in preflight
    assert '${prefix}_READBACK_OK committed=1' in preflight


def test_exam_migration_tests_are_part_of_release_ci():
    workflow = (ROOT / '.github/workflows/ci.yml').read_text()
    assert 'scripts/test_exam_attempts_release.py' in workflow
    assert 'scripts/test_exam_attempts_release_postgres.py' in workflow
    assert 'scripts/test_exam_release_wiring.py' in workflow
    assert 'tests/test_exam_practice_postgres.py' in workflow
    assert 'EXAM_TEST_DATABASE_URL: postgresql://' in workflow


def test_exam_postgres_ci_keeps_app_import_out_of_default_database():
    import yaml
    workflow = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())
    step = next(step for step in workflow['jobs']['agent-runtime-postgres']['steps']
                if step.get('name') == 'Verify exam practice PostgreSQL transactions')
    assert step['env']['DATABASE_URL'] == 'sqlite:///:memory:'
    assert step['env']['EXAM_TEST_DATABASE_URL'].endswith('/health_runtime_test')
    assert 'tests/test_exam_practice_postgres.py' in step['run']
