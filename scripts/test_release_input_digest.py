import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIGEST_SCRIPT = ROOT / "scripts" / "release_input_digest.py"


def _commit(repo: Path, message: str) -> str:
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=repo, check=True)
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()


def _digest(repo: Path, commit: str, kind: str) -> str:
    result = subprocess.run(
        [
            "python3",
            str(DIGEST_SCRIPT),
            "--repo",
            str(repo),
            "--commit",
            commit,
            "--kind",
            kind,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    value = result.stdout.strip()
    assert len(value) == 64
    return value


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    (repo / "backend/data/system_kb_v2_seed").mkdir(parents=True)
    (repo / "backend/knowledge").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / "backend/requirements.lock").write_text("fastapi==1.0\n")
    (repo / "backend/data/system_kb_v2_seed/pages.jsonl").write_text("{}\n")
    (repo / "backend/knowledge/nutrition.md").write_text("base\n")
    (repo / "docs/readme.md").write_text("base\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "release@example.test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"], cwd=repo, check=True
    )
    return repo, _commit(repo, "base")


def test_release_input_digests_ignore_unrelated_docs_changes(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    base_requirements = _digest(repo, base, "requirements")
    base_kb = _digest(repo, base, "system-kb")
    (repo / "docs/readme.md").write_text("changed\n")
    docs = _commit(repo, "docs")

    assert _digest(repo, docs, "requirements") == base_requirements
    assert _digest(repo, docs, "system-kb") == base_kb


def test_release_input_digests_change_only_for_their_owned_inputs(
    tmp_path: Path,
) -> None:
    repo, base = _repo(tmp_path)
    base_requirements = _digest(repo, base, "requirements")
    base_kb = _digest(repo, base, "system-kb")

    (repo / "backend/data/system_kb_v2_seed/pages.jsonl").write_text(
        '{"id": 1}\n'
    )
    kb_commit = _commit(repo, "kb")
    assert _digest(repo, kb_commit, "system-kb") != base_kb
    assert _digest(repo, kb_commit, "requirements") == base_requirements

    (repo / "backend/requirements.lock").write_text("fastapi==2.0\n")
    requirements_commit = _commit(repo, "requirements")
    assert _digest(repo, requirements_commit, "requirements") != base_requirements
