import importlib.util
import json
import os
import stat
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROOF_SCRIPT = ROOT / "scripts" / "release_step_proof.py"
GOOD_DIGESTS = {
    "input_digest": "1" * 64,
    "toolchain_digest": "2" * 64,
    "output_digest": "3" * 64,
}


def _load_module():
    assert PROOF_SCRIPT.exists(), "release_step_proof.py must exist"
    spec = importlib.util.spec_from_file_location("release_step_proof", PROOF_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _material(module, **overrides):
    values = {**GOOD_DIGESTS, **overrides}
    return module.ProofMaterial(
        input_digest=values["input_digest"],
        toolchain_digest=values["toolchain_digest"],
        output_digest=values["output_digest"],
        postcondition="postcondition-v1",
    )


def _record_valid(module, receipt_root: Path, step: str = "python-dependencies"):
    module.record_receipt(
        receipt_root,
        step,
        _material(module),
        expected_uid=os.getuid(),
    )
    return receipt_root / f"{step}.json"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_missing_receipt_is_a_fail_closed_miss(tmp_path: Path):
    module = _load_module()

    result = module.evaluate_receipt(
        tmp_path / "proofs",
        "python-dependencies",
        _material(module),
        mode="on",
        expected_uid=os.getuid(),
    )

    assert result.should_skip is False
    assert result.candidate_hit is False
    assert result.reason == "missing-receipt"


def test_corrupt_receipt_is_a_fail_closed_miss(tmp_path: Path):
    module = _load_module()
    receipt = _record_valid(module, tmp_path / "proofs")
    receipt.write_text("{not-json\n", encoding="utf-8")

    result = module.evaluate_receipt(
        receipt.parent,
        "python-dependencies",
        _material(module),
        mode="on",
        expected_uid=os.getuid(),
    )

    assert result.should_skip is False
    assert result.reason == "corrupt-receipt"


def test_weak_receipt_permissions_are_rejected(tmp_path: Path):
    module = _load_module()
    receipt = _record_valid(module, tmp_path / "proofs")
    receipt.chmod(0o644)

    result = module.evaluate_receipt(
        receipt.parent,
        "python-dependencies",
        _material(module),
        mode="on",
        expected_uid=os.getuid(),
    )

    assert result.should_skip is False
    assert result.reason == "unsafe-receipt-permissions"


def test_symlink_receipt_is_rejected_without_following_target(tmp_path: Path):
    module = _load_module()
    receipt_root = tmp_path / "proofs"
    receipt_root.mkdir(mode=0o700)
    target = tmp_path / "attacker.json"
    target.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    (receipt_root / "python-dependencies.json").symlink_to(target)

    result = module.evaluate_receipt(
        receipt_root,
        "python-dependencies",
        _material(module),
        mode="on",
        expected_uid=os.getuid(),
    )

    assert result.should_skip is False
    assert result.reason == "unsafe-receipt-type"


def test_symlink_receipt_directory_is_rejected(tmp_path: Path):
    module = _load_module()
    actual = tmp_path / "actual"
    actual.mkdir(mode=0o700)
    linked = tmp_path / "proofs"
    linked.symlink_to(actual, target_is_directory=True)

    result = module.evaluate_receipt(
        linked,
        "python-dependencies",
        _material(module),
        mode="on",
        expected_uid=os.getuid(),
    )

    assert result.should_skip is False
    assert result.reason == "unsafe-receipt-directory"


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("input_digest", "input-drift"),
        ("toolchain_digest", "toolchain-drift"),
        ("output_digest", "output-drift"),
    ],
)
def test_each_proof_dimension_invalidates_reuse(
    tmp_path: Path,
    field: str,
    reason: str,
):
    module = _load_module()
    receipt_root = tmp_path / "proofs"
    _record_valid(module, receipt_root)

    result = module.evaluate_receipt(
        receipt_root,
        "python-dependencies",
        _material(module, **{field: "f" * 64}),
        mode="on",
        expected_uid=os.getuid(),
    )

    assert result.should_skip is False
    assert result.reason == reason


def test_postcondition_contract_drift_invalidates_reuse(tmp_path: Path):
    module = _load_module()
    receipt_root = tmp_path / "proofs"
    _record_valid(module, receipt_root)
    changed = module.ProofMaterial(
        **GOOD_DIGESTS,
        postcondition="postcondition-v2",
    )

    result = module.evaluate_receipt(
        receipt_root,
        "python-dependencies",
        changed,
        mode="on",
        expected_uid=os.getuid(),
    )

    assert result.should_skip is False
    assert result.reason == "postcondition-drift"


def test_off_mode_never_reads_or_reuses_a_valid_receipt(tmp_path: Path):
    module = _load_module()
    receipt_root = tmp_path / "proofs"
    _record_valid(module, receipt_root)

    result = module.evaluate_receipt(
        receipt_root,
        "python-dependencies",
        _material(module),
        mode="off",
        expected_uid=os.getuid(),
    )

    assert result.should_skip is False
    assert result.candidate_hit is False
    assert result.reason == "disabled"


def test_shadow_mode_reports_hit_but_never_skips(tmp_path: Path):
    module = _load_module()
    receipt_root = tmp_path / "proofs"
    _record_valid(module, receipt_root)

    result = module.evaluate_receipt(
        receipt_root,
        "python-dependencies",
        _material(module),
        mode="shadow",
        expected_uid=os.getuid(),
    )

    assert result.should_skip is False
    assert result.candidate_hit is True
    assert result.reason == "shadow-hit"


def test_on_mode_reuses_only_a_complete_matching_receipt(tmp_path: Path):
    module = _load_module()
    receipt_root = tmp_path / "proofs"
    _record_valid(module, receipt_root)

    result = module.evaluate_receipt(
        receipt_root,
        "python-dependencies",
        _material(module),
        mode="on",
        expected_uid=os.getuid(),
    )

    assert result.should_skip is True
    assert result.candidate_hit is True
    assert result.reason == "hit"


def test_receipt_write_is_atomic_private_and_complete(tmp_path: Path):
    module = _load_module()
    receipt_root = tmp_path / "proofs"

    receipt = _record_valid(module, receipt_root)

    assert stat.S_IMODE(receipt_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert list(receipt_root.glob("*.tmp")) == []
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["step"] == "python-dependencies"
    assert payload["input_digest"] == GOOD_DIGESTS["input_digest"]
    assert payload["toolchain_digest"] == GOOD_DIGESTS["toolchain_digest"]
    assert payload["output_digest"] == GOOD_DIGESTS["output_digest"]
    assert payload["postcondition"] == "postcondition-v1"


def test_failed_step_does_not_write_a_receipt(tmp_path: Path):
    module = _load_module()
    receipt_root = tmp_path / "proofs"

    with pytest.raises(RuntimeError, match="install failed"):
        module.execute_and_record(
            receipt_root=receipt_root,
            step="python-dependencies",
            mode="shadow",
            current_material=lambda: _material(module),
            action=lambda: (_ for _ in ()).throw(RuntimeError("install failed")),
            postcondition=lambda: None,
            expected_uid=os.getuid(),
        )

    assert not (receipt_root / "python-dependencies.json").exists()


def test_failed_postcondition_does_not_write_a_receipt(tmp_path: Path):
    module = _load_module()
    receipt_root = tmp_path / "proofs"
    actions = []

    with pytest.raises(RuntimeError, match="postcondition failed"):
        module.execute_and_record(
            receipt_root=receipt_root,
            step="frontend-build",
            mode="shadow",
            current_material=lambda: _material(module),
            action=lambda: actions.append("built"),
            postcondition=lambda: (_ for _ in ()).throw(
                RuntimeError("postcondition failed")
            ),
            expected_uid=os.getuid(),
        )

    assert actions == ["built"]
    assert not (receipt_root / "frontend-build.json").exists()


def test_failed_shadow_rerun_invalidates_the_previous_receipt(tmp_path: Path):
    module = _load_module()
    receipt_root = tmp_path / "proofs"
    receipt = _record_valid(module, receipt_root)

    with pytest.raises(RuntimeError, match="install failed"):
        module.execute_and_record(
            receipt_root=receipt_root,
            step="python-dependencies",
            mode="shadow",
            current_material=lambda: _material(module),
            action=lambda: (_ for _ in ()).throw(RuntimeError("install failed")),
            postcondition=lambda: None,
            expected_uid=os.getuid(),
        )

    assert not receipt.exists()


def test_profile_names_and_production_cache_root_are_fixed():
    module = _load_module()

    assert module.DEFAULT_RECEIPT_ROOT == Path("/var/cache/health-app/release-proofs")
    assert set(module.PROFILES) == {
        "python-dependencies",
        "frontend-dependencies",
        "frontend-build",
    }


def test_python_dependency_profile_tracks_lock_toolchain_and_installed_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load_module()
    backend = tmp_path / "backend"
    python = backend / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    (backend / "requirements.lock").write_text("package==1 --hash=sha256:abc\n")
    _write_executable(
        python,
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        'if [ "$1" = "--version" ]; then printf \'%s\\n\' "$FAKE_PYTHON_VERSION"; exit; fi\n'
        'if [ "${1:-} ${2:-} ${3:-}" = "-m pip --version" ]; then '
        "printf 'pip %s\\n' \"$FAKE_PIP_VERSION\"; exit; fi\n"
        'if [ "${1:-} ${2:-} ${3:-}" = "-m pip check" ]; then '
        'exit "${FAKE_PIP_CHECK_RC:-0}"; fi\n'
        'if [ "$1" = "-c" ]; then printf \'%s\\n\' "$FAKE_DISTRIBUTIONS"; exit; fi\n'
        "exit 90\n",
    )
    monkeypatch.setenv("FAKE_PYTHON_VERSION", "Python 3.12.9")
    monkeypatch.setenv("FAKE_PIP_VERSION", "25.1")
    monkeypatch.setenv("FAKE_DISTRIBUTIONS", '[["package","1"]]')

    first = module.collect_python_dependencies_material(
        backend,
        expected_uid=os.getuid(),
        python_executable=python,
    )
    (backend / "requirements.lock").write_text("package==2 --hash=sha256:def\n")
    lock_changed = module.collect_python_dependencies_material(
        backend,
        expected_uid=os.getuid(),
        python_executable=python,
    )
    monkeypatch.setenv("FAKE_PYTHON_VERSION", "Python 3.13.0")
    toolchain_changed = module.collect_python_dependencies_material(
        backend,
        expected_uid=os.getuid(),
        python_executable=python,
    )
    monkeypatch.setenv("FAKE_DISTRIBUTIONS", '[["package","2"]]')
    output_changed = module.collect_python_dependencies_material(
        backend,
        expected_uid=os.getuid(),
        python_executable=python,
    )

    assert first.input_digest != lock_changed.input_digest
    assert lock_changed.toolchain_digest != toolchain_changed.toolchain_digest
    assert toolchain_changed.output_digest != output_changed.output_digest
    assert first.postcondition == "pip-check-venv-owner-v1"


def test_python_profile_uses_non_reusable_output_when_pip_check_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load_module()
    backend = tmp_path / "backend"
    python = backend / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    (backend / "requirements.lock").write_text("package==1\n")
    _write_executable(
        python,
        "#!/bin/bash\n"
        'if [ "$1" = "--version" ]; then echo \'Python 3.12\'; exit; fi\n'
        'if [ "${1:-} ${2:-} ${3:-}" = "-m pip --version" ]; then echo \'pip 25\'; exit; fi\n'
        'if [ "${1:-} ${2:-} ${3:-}" = "-m pip check" ]; then exit 1; fi\n'
        "exit 90\n",
    )

    material = module.collect_python_dependencies_material(
        backend,
        expected_uid=os.getuid(),
        python_executable=python,
        allow_missing_output=True,
    )

    assert material.output_digest == module.UNAVAILABLE_OUTPUT_DIGEST
    with pytest.raises(module.ProfileUnavailable, match="pip check"):
        module.collect_python_dependencies_material(
            backend,
            expected_uid=os.getuid(),
            python_executable=python,
        )


def test_python_profile_accepts_standard_venv_python_symlink(
    tmp_path: Path,
):
    module = _load_module()
    backend = tmp_path / "backend"
    bin_dir = backend / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    target = bin_dir / "python3"
    python = bin_dir / "python"
    (backend / "requirements.lock").write_text("package==1\n")
    _write_executable(
        target,
        "#!/bin/bash\n"
        'if [ "${1:-}" = "--version" ]; then echo \'Python 3.12\'; exit; fi\n'
        'if [ "${1:-} ${2:-} ${3:-}" = "-m pip --version" ]; then echo \'pip 25\'; exit; fi\n'
        'if [ "${1:-} ${2:-} ${3:-}" = "-m pip check" ]; then exit 0; fi\n'
        'if [ "${1:-}" = "-c" ]; then echo \'[["package","1"]]\'; exit; fi\n'
        "exit 90\n",
    )
    python.symlink_to("python3")

    material = module.collect_python_dependencies_material(
        backend,
        expected_uid=os.getuid(),
        python_executable=python,
    )

    assert material.output_digest != module.UNAVAILABLE_OUTPUT_DIGEST


def test_standard_symlink_mode_bits_do_not_make_toolchain_unsafe():
    module = _load_module()

    class FakeSymlink:
        name = "python"

        def lstat(self):
            return SimpleNamespace(
                st_mode=stat.S_IFLNK | 0o777,
                st_uid=os.getuid(),
            )

        def is_symlink(self):
            return True

    info = module._safe_path_info(
        FakeSymlink(),
        expected_uid=os.getuid(),
        kind="venv python",
        allow_symlink=True,
    )

    assert stat.S_ISLNK(info.st_mode)


def test_python_profile_rejects_group_writable_symlink_target(
    tmp_path: Path,
):
    module = _load_module()
    backend = tmp_path / "backend"
    bin_dir = backend / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    target = bin_dir / "python3"
    python = bin_dir / "python"
    (backend / "requirements.lock").write_text("package==1\n")
    _write_executable(target, "#!/bin/sh\nexit 0\n")
    target.chmod(0o777)
    python.symlink_to("python3")

    with pytest.raises(module.ProfileUnavailable, match="group/world writable"):
        module.collect_python_dependencies_material(
            backend,
            expected_uid=os.getuid(),
            python_executable=python,
        )


def _frontend_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    frontend = tmp_path / "repo" / "frontend"
    node_modules = frontend / "node_modules"
    node_modules.mkdir(parents=True)
    (frontend / "package.json").write_text('{"name":"frontend"}\n')
    (frontend / "package-lock.json").write_text('{"lockfileVersion":3}\n')
    (node_modules / ".package-lock.json").write_text('{"lockfileVersion":3}\n')
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "node", '#!/bin/sh\necho "${FAKE_NODE_VERSION:-v22}"\n'
    )
    _write_executable(
        fake_bin / "npm",
        "#!/bin/bash\n"
        'if [ "$1" = "--version" ]; then echo "${FAKE_NPM_VERSION:-10}"; exit; fi\n'
        'if [ "${1:-} ${2:-} ${3:-}" = "ls --all --json" ]; then '
        'if [ "$PWD" != "$FAKE_NPM_EXPECTED_CWD" ]; then exit 88; fi; '
        'printf \'%s\\n\' "$FAKE_NPM_TREE"; exit "${FAKE_NPM_LS_RC:-0}"; fi\n'
        "exit 90\n",
    )
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    monkeypatch.setenv(
        "FAKE_NPM_TREE",
        '{"name":"frontend","dependencies":{"next":{"version":"15.1.0"}}}',
    )
    monkeypatch.setenv("FAKE_NPM_EXPECTED_CWD", str(frontend))
    return frontend, node_modules


def test_frontend_dependency_profile_tracks_inputs_toolchain_and_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load_module()
    frontend, node_modules = _frontend_fixture(tmp_path, monkeypatch)

    first = module.collect_frontend_dependencies_material(
        frontend,
        expected_uid=os.getuid(),
    )
    (frontend / "package.json").write_text('{"name":"changed"}\n')
    input_changed = module.collect_frontend_dependencies_material(
        frontend,
        expected_uid=os.getuid(),
    )
    monkeypatch.setenv("FAKE_NODE_VERSION", "v24")
    toolchain_changed = module.collect_frontend_dependencies_material(
        frontend,
        expected_uid=os.getuid(),
    )
    (node_modules / ".package-lock.json").write_text(
        '{"lockfileVersion":3,"changed":true}\n'
    )
    output_changed = module.collect_frontend_dependencies_material(
        frontend,
        expected_uid=os.getuid(),
    )

    assert first.input_digest != input_changed.input_digest
    assert input_changed.toolchain_digest != toolchain_changed.toolchain_digest
    assert toolchain_changed.output_digest != output_changed.output_digest
    assert first.postcondition == "npm-ls-node-modules-owner-v1"


def test_frontend_dependency_profile_rejects_writable_toolchain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load_module()
    frontend, _ = _frontend_fixture(tmp_path, monkeypatch)
    node = Path(module.shutil.which("node"))
    node.chmod(0o777)

    with pytest.raises(module.ProfileUnavailable, match="group/world writable"):
        module.collect_frontend_dependencies_material(
            frontend,
            expected_uid=os.getuid(),
        )


def test_frontend_build_profile_tracks_tree_env_dependency_and_next_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load_module()
    frontend, _ = _frontend_fixture(tmp_path, monkeypatch)
    next_output = frontend / ".next"
    next_output.mkdir()
    (next_output / "BUILD_ID").write_text("build-one\n")
    repo = frontend.parent
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "release@example.test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "add", "frontend/package.json", "frontend/package-lock.json"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    monkeypatch.setenv("NEXT_PUBLIC_API_URL", "https://api-one.example")

    first = module.collect_frontend_build_material(
        frontend,
        expected_uid=os.getuid(),
    )
    monkeypatch.setenv("NEXT_PUBLIC_API_URL", "https://api-two.example")
    env_changed = module.collect_frontend_build_material(
        frontend,
        expected_uid=os.getuid(),
    )
    (next_output / "BUILD_ID").write_text("build-two\n")
    output_changed = module.collect_frontend_build_material(
        frontend,
        expected_uid=os.getuid(),
    )

    assert first.input_digest != env_changed.input_digest
    assert env_changed.output_digest != output_changed.output_digest
    assert first.postcondition == "frontend-pm2-http-v1"


def test_frontend_build_profile_rejects_symlinked_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load_module()
    frontend, _ = _frontend_fixture(tmp_path, monkeypatch)
    next_output = frontend / ".next"
    next_output.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("secret\n")
    (next_output / "linked").symlink_to(outside)
    repo = frontend.parent
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "release@example.test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "add", "frontend/package.json", "frontend/package-lock.json"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)

    with pytest.raises(module.ProfileUnavailable, match="symlink"):
        module.collect_frontend_build_material(
            frontend,
            expected_uid=os.getuid(),
        )


def test_frontend_build_profile_excludes_mutable_next_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load_module()
    frontend, _ = _frontend_fixture(tmp_path, monkeypatch)
    next_output = frontend / ".next"
    cache = next_output / "cache"
    cache.mkdir(parents=True)
    (next_output / "BUILD_ID").write_text("served-build\n")
    cached = cache / "webpack.bin"
    cached.write_text("cache-one\n")
    repo = frontend.parent
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "release@example.test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "add", "frontend/package.json", "frontend/package-lock.json"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)

    first = module.collect_frontend_build_material(
        frontend,
        expected_uid=os.getuid(),
    )
    cached.write_text("cache-two\n")
    second = module.collect_frontend_build_material(
        frontend,
        expected_uid=os.getuid(),
    )

    assert first.output_digest == second.output_digest


def test_frontend_build_profile_tracks_uncommitted_next_env_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load_module()
    frontend, _ = _frontend_fixture(tmp_path, monkeypatch)
    next_output = frontend / ".next"
    next_output.mkdir()
    (next_output / "BUILD_ID").write_text("served-build\n")
    build_env = frontend / ".env.production"
    build_env.write_text("BACKEND_URL=https://api-one.example\n")
    repo = frontend.parent
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "release@example.test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "add", "frontend/package.json", "frontend/package-lock.json"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)

    first = module.collect_frontend_build_material(
        frontend,
        expected_uid=os.getuid(),
    )
    build_env.write_text("BACKEND_URL=https://api-two.example\n")
    second = module.collect_frontend_build_material(
        frontend,
        expected_uid=os.getuid(),
    )

    assert first.input_digest != second.input_digest


def test_cli_help_exposes_only_the_fixed_profiles():
    result = subprocess.run(
        ["python3", str(PROOF_SCRIPT), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "python-dependencies" in result.stdout
    assert "frontend-dependencies" in result.stdout
    assert "frontend-build" in result.stdout
    assert "--expected-owner-uid" not in result.stdout


def test_cli_off_mode_neither_probes_nor_creates_receipts(tmp_path: Path):
    receipt_root = tmp_path / "proofs"
    missing_workspace = tmp_path / "missing"

    result = subprocess.run(
        [
            "python3",
            str(PROOF_SCRIPT),
            "check",
            "--mode",
            "off",
            "--profile",
            "python-dependencies",
            "--workspace",
            str(missing_workspace),
            "--root",
            str(receipt_root),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3, (result.stdout, result.stderr)
    payload = json.loads(result.stdout)
    assert payload == {
        "candidate_hit": False,
        "mode": "off",
        "reason": "disabled",
        "skip": False,
        "step": "python-dependencies",
    }
    assert not receipt_root.exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="non-root refusal test")
def test_cli_refuses_to_record_non_root_owned_production_proof(tmp_path: Path):
    result = subprocess.run(
        [
            "python3",
            str(PROOF_SCRIPT),
            "record",
            "--mode",
            "shadow",
            "--profile",
            "python-dependencies",
            "--workspace",
            str(tmp_path / "backend"),
            "--root",
            str(tmp_path / "proofs"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "requires root" in result.stderr
    assert not (tmp_path / "proofs").exists()
