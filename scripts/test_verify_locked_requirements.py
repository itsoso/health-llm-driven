import importlib.metadata
import subprocess
import sys
from pathlib import Path

import pytest

import backend.scripts.verify_locked_requirements as verifier


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "backend" / "scripts" / "verify_locked_requirements.py"


def _run(lock: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER), str(lock)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_locked_requirement_verifier_accepts_exact_installed_version(
    tmp_path: Path,
) -> None:
    version = importlib.metadata.version("pip")
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        f"pip=={version} \\\n    --hash=sha256:{'a' * 64}\n",
        encoding="utf-8",
    )

    result = _run(lock)

    assert result.returncode == 0, result.stderr
    assert "LOCKED_REQUIREMENTS_OK packages=1" in result.stdout


def test_locked_requirement_verifier_rejects_mismatch_and_unpinned_input(
    tmp_path: Path,
) -> None:
    mismatch = tmp_path / "mismatch.lock"
    mismatch.write_text(
        f"pip==0.0.1 \\\n    --hash=sha256:{'a' * 64}\n",
        encoding="utf-8",
    )
    unpinned = tmp_path / "unpinned.lock"
    unpinned.write_text("pip>=1\n", encoding="utf-8")

    mismatch_result = _run(mismatch)
    unpinned_result = _run(unpinned)

    assert mismatch_result.returncode != 0
    assert "installed=" in mismatch_result.stderr
    assert unpinned_result.returncode != 0
    assert "unsupported lock requirement" in unpinned_result.stderr


@pytest.mark.parametrize(
    ("package_name", "installed_version"),
    (("chromadb", "0.6.3"), ("chroma-hnswlib", "0.7.6")),
)
def test_locked_requirement_verifier_rejects_stale_unpatched_chroma_packages(
    tmp_path: Path,
    monkeypatch,
    package_name: str,
    installed_version: str,
) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "pip==1.0 \\\n    --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )

    def fake_version(name: str) -> str:
        normalized = name.lower().replace("_", "-")
        if normalized == "pip":
            return "1.0"
        if normalized == package_name:
            return installed_version
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(verifier.importlib.metadata, "version", fake_version)

    assert verifier.verify_lock(lock) == [
        f"{package_name}: forbidden installed package; installed={installed_version}"
    ]


def test_locked_requirement_verifier_can_sanitize_forbidden_entries_from_a_rollback_lock(
    tmp_path: Path,
    monkeypatch,
) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "pip==1.0 \\\n"
        "    --hash=sha256:" + "a" * 64 + "\n"
        "chromadb==0.6.3 \\\n"
        "    --hash=sha256:" + "b" * 64 + "\n"
        "chroma-hnswlib==0.7.6 \\\n"
        "    --hash=sha256:" + "c" * 64 + "\n",
        encoding="utf-8",
    )

    installed_forbidden: dict[str, str] = {}

    def fake_version(name: str) -> str:
        normalized = name.lower().replace("_", "-")
        if normalized == "pip":
            return "1.0"
        if normalized in installed_forbidden:
            return installed_forbidden[normalized]
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(verifier.importlib.metadata, "version", fake_version)

    assert (
        verifier.verify_lock(
            lock,
            sanitize_forbidden_packages=True,
        )
        == []
    )
    installed_forbidden["chroma-hnswlib"] = "0.7.6"
    assert verifier.verify_lock(
        lock,
        sanitize_forbidden_packages=True,
    ) == ["chroma-hnswlib: forbidden installed package; installed=0.7.6"]


@pytest.fixture
def runtime_identity(monkeypatch):
    import os
    from types import SimpleNamespace

    uid = os.getuid()
    if uid == 0:
        pytest.skip("Runtime filesystem probes require an actual non-root process")
    # Only account lookup is synthetic; actual UID and all permission checks
    # remain the operating system's real unprivileged process identity.
    monkeypatch.setattr(
        verifier.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=uid)
    )
    return uid


def runtime_distribution(tmp_path, monkeypatch):
    import csv

    root = tmp_path / "venv"
    root.mkdir()
    package = root / "demo"
    package.mkdir()
    code = package / "__init__.py"
    code.write_text("VALUE = 1\n")
    metadata = root / "demo-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text("Name: demo\nVersion: 1.0\n")
    record = metadata / "RECORD"
    with record.open("w", newline="") as stream:
        csv.writer(stream).writerows(
            [
                ["demo/__init__.py", "", ""],
                ["demo-1.0.dist-info/METADATA", "", ""],
                ["demo-1.0.dist-info/RECORD", "", ""],
            ]
        )
    dist = importlib.metadata.PathDistribution(metadata)

    def fake_version(name):
        if name == "demo":
            return "1.0"
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(verifier.importlib.metadata, "version", fake_version)
    monkeypatch.setattr(verifier.importlib.metadata, "distribution", lambda name: dist)
    monkeypatch.setattr(verifier.sys, "prefix", str(root))
    lock = tmp_path / "requirements.lock"
    lock.write_text("demo==1.0\n")
    return lock, package, code, record


@pytest.mark.parametrize("actual", [0, 99999])
def test_runtime_user_rejects_root_or_wrong_actual_identity(
    tmp_path, monkeypatch, actual
):
    from types import SimpleNamespace

    lock = tmp_path / "requirements.lock"
    lock.write_text("pip==1\n")
    monkeypatch.setattr(
        verifier.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=12345)
    )
    monkeypatch.setattr(verifier.os, "getuid", lambda: actual)
    monkeypatch.setattr(verifier.os, "geteuid", lambda: actual)
    assert "runtime identity" in " ".join(
        verifier.verify_lock(lock, runtime_user="health-app")
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "unreadable_code",
        "untraversable_package",
        "missing_code",
        "missing_record",
        "outside_prefix",
    ],
)
def test_runtime_readability_rejects_broken_files_despite_valid_metadata(
    tmp_path, monkeypatch, runtime_identity, mutation
):
    import os

    lock, package, code, record = runtime_distribution(tmp_path, monkeypatch)
    if mutation.startswith("un") and os.getuid() == 0:
        pytest.skip("Permission-denial fixture requires a real non-root process")
    if mutation == "unreadable_code":
        code.chmod(0)
    elif mutation == "untraversable_package":
        package.chmod(0o600)
    elif mutation == "missing_code":
        code.unlink()
    elif mutation == "missing_record":
        record.unlink()
    else:
        outside = tmp_path / "not-a-package-secret"
        outside.write_text("synthetic private sentinel")
        record.write_text(record.read_text() + "../not-a-package-secret,,\n")
    try:
        assert verifier.verify_lock(lock) == []  # Old metadata-only gate passes.
        errors = verifier.verify_lock(lock, runtime_user="health-app")
        assert errors and any("RECORD" in error for error in errors)
        if mutation in {"unreadable_code", "untraversable_package"}:
            assert "PermissionError" in " ".join(errors)
        assert "synthetic private sentinel" not in " ".join(errors)
    finally:
        package.chmod(0o755)
        if code.exists():
            code.chmod(0o644)


def test_runtime_pyjwt_real_locked_distribution_roundtrip(tmp_path, runtime_identity):
    lock = tmp_path / "requirements.lock"
    lock.write_text(f"PyJWT=={importlib.metadata.version('PyJWT')}\n")
    assert verifier.verify_lock(lock, runtime_user="health-app") == []


def test_runtime_namespace_jwt_is_not_a_working_locked_distribution(
    tmp_path, monkeypatch, runtime_identity
):
    from types import SimpleNamespace

    lock = tmp_path / "requirements.lock"
    lock.write_text(f"PyJWT=={importlib.metadata.version('PyJWT')}\n")
    monkeypatch.setattr(
        verifier.importlib, "import_module", lambda name: SimpleNamespace(__file__=None)
    )
    errors = verifier.verify_lock(lock, runtime_user="health-app")
    assert errors and "PyJWT" in " ".join(errors)


@pytest.mark.parametrize(
    "mutation",
    [
        "accept_wrong_signature",
        "accept_invalid_token",
        "foreign_origin",
        "leaky_exception",
    ],
)
def test_runtime_pyjwt_rejects_broken_crypto_and_never_reports_tokens(
    tmp_path, monkeypatch, runtime_identity, mutation
):
    import jwt

    lock = tmp_path / "requirements.lock"
    lock.write_text(f"PyJWT=={importlib.metadata.version('PyJWT')}\n")
    if mutation == "foreign_origin":
        monkeypatch.setattr(jwt, "__file__", str(tmp_path / "foreign-jwt.py"))
        (tmp_path / "foreign-jwt.py").write_text("synthetic")
    else:
        decode = jwt.decode
        calls = []

        def broken_decode(token, key, **kwargs):
            calls.append(token)
            if mutation == "leaky_exception":
                raise RuntimeError("synthetic-secret-do-not-log " + token)
            if (mutation == "accept_wrong_signature" and len(calls) == 2) or (
                mutation == "accept_invalid_token" and len(calls) == 3
            ):
                return {"sub": "runtime-readability-probe"}
            return decode(token, key, **kwargs)

        broken_decode.__module__ = "jwt.api_jwt"
        monkeypatch.setattr(jwt, "decode", broken_decode)
    errors = verifier.verify_lock(lock, runtime_user="health-app")
    assert errors and "PyJWT" in " ".join(errors)
    assert "synthetic-secret-do-not-log" not in " ".join(errors)


def test_runtime_cli_uses_real_nonroot_account_and_keeps_flags_compatible(tmp_path):
    import os
    import pwd

    if os.getuid() == 0:
        pytest.skip("Real-account success fixture requires non-root execution")
    username = pwd.getpwuid(os.getuid()).pw_name
    lock = tmp_path / "requirements.lock"
    lock.write_text(f"PyJWT=={importlib.metadata.version('PyJWT')}\nchromadb==0.6.3\n")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(VERIFIER),
            "--runtime-user",
            username,
            "--sanitize-forbidden-packages",
            str(lock),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "LOCKED_REQUIREMENTS_OK packages=2\n"
    assert result.stderr == ""


def test_runtime_cli_unknown_user_fails_without_loading_application(tmp_path):
    lock = tmp_path / "requirements.lock"
    lock.write_text("pip==1\n")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(VERIFIER),
            "--runtime-user",
            "reva-no-such-account-947819",
            str(lock),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "runtime identity" in result.stderr
    assert "LOCKED_REQUIREMENTS_OK" not in result.stdout


def test_runtime_record_csv_must_not_silently_discard_malformed_entries(
    tmp_path, monkeypatch, runtime_identity
):
    lock, _, _, record = runtime_distribution(tmp_path, monkeypatch)
    record.write_text(record.read_text() + "unparsed-entry\n")
    assert "malformed installed RECORD" in " ".join(
        verifier.verify_lock(lock, runtime_user="health-app")
    )
