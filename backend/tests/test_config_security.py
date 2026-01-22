import pytest
from app.config import Settings


def test_settings_rejects_default_secret_key():
    settings = Settings(secret_key="your-super-secret-key-change-in-production")
    with pytest.raises(ValueError):
        settings.validate_required_security()


def test_settings_accepts_strong_secret_key():
    settings = Settings(secret_key="A" * 32)
    settings.validate_required_security()
