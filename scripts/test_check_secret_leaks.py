import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("check_secret_leaks.py")
SPEC = importlib.util.spec_from_file_location("check_secret_leaks", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_runtime_env_and_backup_names_are_rejected():
    assert MODULE.SENSITIVE_NAMES.search(".env")
    assert MODULE.SENSITIVE_NAMES.search("backend/.env.production")
    assert MODULE.SENSITIVE_NAMES.search("backend/.env.backup.20260721")
    assert not MODULE.SENSITIVE_NAMES.search(".env.example")


def test_realistic_secrets_match_but_placeholders_do_not():
    samples = {
        "LTAI" + "1234567890abcdefgh": True,
        "sk-" + "1234567890abcdefghijklmnop": True,
        "sk-xxx": False,
        "LTAI...": False,
    }
    for value, expected in samples.items():
        matched = any(
            pattern.search(value.encode()) for _, pattern in MODULE.SECRET_PATTERNS
        )
        assert matched is expected


def test_placeholder_marker_suppresses_documented_fake_key(tmp_path, monkeypatch):
    fake = tmp_path / "fake.md"
    fake.write_text("sk-your-example-placeholder-key", encoding="utf-8")
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)

    assert MODULE.scan(["fake.md"]) == []
