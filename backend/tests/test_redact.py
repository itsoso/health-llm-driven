from app.utils.redact import mask_email


def test_mask_email_basic():
    assert mask_email("alice@example.com") == "a***@example.com"


def test_mask_email_short_local():
    assert mask_email("a@b.com") == "a***@b.com"


def test_mask_email_invalid():
    assert mask_email("") == "<redacted>"
    assert mask_email(None) == "<redacted>"
    assert mask_email("notanemail") == "<redacted>"
