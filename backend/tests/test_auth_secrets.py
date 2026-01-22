from app.config import settings
from app.services import auth


def test_auth_uses_settings_secret_key():
    assert auth.SECRET_KEY == settings.secret_key
