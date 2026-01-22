from app.config import Settings


def test_cors_origins_parse():
    settings = Settings(cors_allow_origins="https://a.com,https://b.com")
    assert settings.cors_allow_origins_list == ["https://a.com", "https://b.com"]
