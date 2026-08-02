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


@pytest.mark.parametrize(
    "missing_field",
    [
        "aliyun_sms_access_key_id",
        "aliyun_sms_access_key_secret",
        "registration_invitation_sms_sign_name",
        "registration_invitation_sms_template_code",
    ],
)
def test_production_invitation_rollout_requires_dedicated_sms_config(missing_field):
    values = {
        "aliyun_sms_access_key_id": "invite-access-id",
        "aliyun_sms_access_key_secret": "invite-access-secret",
        "registration_invitation_sms_sign_name": "小巴邀请",
        "registration_invitation_sms_template_code": "SMS_INVITE_123",
    }
    secret = values[missing_field]
    values[missing_field] = None
    configured = Settings(
        _env_file=None,
        secret_key="A" * 32,
        app_env="production",
        debug=False,
        garmin_encryption_key="B" * 44,
        device_encryption_key="C" * 44,
        registration_invitation_digest_key="D" * 32,
        registration_invitation_rollout_enabled=True,
        **values,
    )

    with pytest.raises(ValueError) as exc_info:
        configured.validate_required_security()

    assert "registration invitation SMS" in str(exc_info.value)
    assert secret not in str(exc_info.value)


def test_production_invitation_sms_accepts_effective_fallback_access_keys():
    configured = Settings(
        _env_file=None,
        secret_key="A" * 32,
        app_env="production",
        debug=False,
        garmin_encryption_key="B" * 44,
        device_encryption_key="C" * 44,
        registration_invitation_digest_key="D" * 32,
        registration_invitation_enforcement_enabled=True,
        aliyun_access_key_id="fallback-id",
        aliyun_access_key_secret="fallback-secret",
        registration_invitation_sms_sign_name="小巴邀请",
        registration_invitation_sms_template_code="SMS_INVITE_123",
    )

    configured.validate_required_security()


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
