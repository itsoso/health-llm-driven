from pathlib import Path

import pytest

from app.config import Settings


def test_settings_rejects_default_secret_key():
    settings = Settings(secret_key="your-super-secret-key-change-in-production")
    with pytest.raises(ValueError):
        settings.validate_required_security()


def test_settings_accepts_strong_secret_key():
    settings = Settings(
        _env_file=None,
        secret_key="A" * 32,
        app_env="test",
        garmin_encryption_key="B" * 44,
        device_encryption_key="C" * 44,
    )
    settings.validate_required_security()


def test_production_rejects_debug():
    settings = Settings(
        _env_file=None,
        secret_key="A" * 32,
        app_env="production",
        debug=True,
        garmin_encryption_key="B" * 44,
        device_encryption_key="C" * 44,
    )
    with pytest.raises(ValueError, match="DEBUG"):
        settings.validate_required_security()


def test_production_security_checks_are_case_insensitive():
    settings = Settings(
        _env_file=None,
        secret_key="A" * 32,
        app_env="PRODUCTION",
        debug=True,
        garmin_encryption_key="B" * 44,
        device_encryption_key="C" * 44,
    )
    with pytest.raises(ValueError, match="DEBUG"):
        settings.validate_required_security()


def test_production_rejects_implicit_llm_recovery():
    settings = Settings(
        _env_file=None,
        secret_key="A" * 32,
        app_env="production",
        debug=False,
        llm_auto_recovery_enabled=True,
        llm_recovery_model_id=None,
        garmin_encryption_key="B" * 44,
        device_encryption_key="C" * 44,
    )
    with pytest.raises(ValueError, match="LLM_RECOVERY_MODEL_ID"):
        settings.validate_required_security()


def test_backup_and_migration_scripts_do_not_embed_database_credentials():
    repo_root = Path(__file__).resolve().parents[2]
    files = (
        repo_root / "backend/scripts/backup_db.sh",
        repo_root / "backend/scripts/verify_backup.sh",
        repo_root / "backend/scripts/migrate_critical_data.py",
        repo_root / "backend/scripts/migrate_data_now.py",
    )
    forbidden = ("HealthDB2026Pass", "health2026", "health_password_2026")
    for path in files:
        content = path.read_text(encoding="utf-8")
        assert not any(value in content for value in forbidden), path
