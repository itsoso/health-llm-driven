from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_dependencies_pin_patched_security_versions():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()

    expected = {
        "fastapi==0.139.2",
        "starlette==1.3.1",
        "python-dotenv==1.2.2",
        "python-multipart==0.0.32",
        "pillow==12.3.0",
        "cryptography==49.0.0",
        "pyjwt==2.13.0",
        "garminconnect==0.3.6",
        "curl_cffi==0.15.0",
        "pdfplumber==0.11.10",
        "pyasn1==0.6.4",
    }
    assert expected.issubset(set(requirements.splitlines()))
    assert "python-jose" not in requirements
    assert "pytest==" not in requirements


def test_test_dependencies_are_separate_from_production():
    dev = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").lower()

    assert "-r requirements.txt" not in dev
    assert "pytest==9.1.1" in dev


def test_production_lock_is_hashed_and_deploy_requires_hashes():
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    deploy = (ROOT.parent / "deploy.sh").read_text(encoding="utf-8")

    assert "--hash=sha256:" in lock
    assert "pip install --require-hashes -r requirements.lock" in deploy


def test_auth_uses_pyjwt_and_keeps_two_year_lifetime():
    auth = (ROOT / "app/services/auth.py").read_text(encoding="utf-8")

    assert "import jwt" in auth
    assert "from jose" not in auth
    assert "ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 365 * 2" in auth
