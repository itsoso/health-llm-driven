import hashlib
import json
import os
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate-api-types.sh"
LOCK_FILE = ROOT / "backend" / "requirements.lock"


def _dry_run(*args: str, cache_root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "API_TYPES_DRY_RUN": "1",
            "API_TYPES_CACHE_ROOT": str(cache_root),
        }
    )
    return subprocess.run(
        [str(GENERATOR), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_generator_cache_is_addressed_by_locked_requirements(tmp_path: Path) -> None:
    result = _dry_run("--check", cache_root=tmp_path)

    assert result.returncode == 0, result.stderr
    digest = hashlib.sha256(LOCK_FILE.read_bytes()).hexdigest()
    assert str(tmp_path / f"python312-{digest}") in result.stdout
    assert "pip install --require-hashes" in result.stdout
    assert "requirements.lock" in result.stdout


def test_generator_check_mode_uses_temporary_outputs_without_copying(
    tmp_path: Path,
) -> None:
    result = _dry_run("--check", cache_root=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "mobile/types/api.generated.ts" in result.stdout
    assert "frontend/src/types/api.generated.ts" in result.stdout
    assert "cmp" in result.stdout
    assert "cp " not in result.stdout


def test_generator_write_mode_updates_both_clients(tmp_path: Path) -> None:
    result = _dry_run(cache_root=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "cp " in result.stdout
    assert "mobile/types/api.generated.ts" in result.stdout
    assert "frontend/src/types/api.generated.ts" in result.stdout


def test_generator_rejects_unknown_modes(tmp_path: Path) -> None:
    result = _dry_run("--unknown", cache_root=tmp_path)

    assert result.returncode != 0
    assert "--check" in result.stderr


def test_package_scripts_share_the_locked_generator() -> None:
    mobile = json.loads((ROOT / "mobile" / "package.json").read_text())
    frontend = json.loads((ROOT / "frontend" / "package.json").read_text())

    for package in (mobile, frontend):
        command = package["scripts"]["generate-types"]
        assert "../scripts/generate-api-types.sh" in command
        assert "source venv/bin/activate" not in command


def test_type_drift_ci_uses_installed_locked_runtime_and_shared_generator() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["type-drift"]
    run_bodies = "\n".join(
        str(step.get("run") or "")
        for step in job["steps"]
        if isinstance(step, dict)
    )
    generator_step = next(
        step
        for step in job["steps"]
        if step.get("name") == "Regenerate client types + assert no drift"
    )

    assert "scripts/generate-api-types.sh --check" in run_bodies
    assert generator_step["env"]["API_TYPES_USE_CURRENT_ENV"] == "1"
    assert generator_step["env"]["API_TYPES_PYTHON"] == "python"
    assert "openapi-typescript@7.13.0 /tmp/openapi.json" not in run_bodies
