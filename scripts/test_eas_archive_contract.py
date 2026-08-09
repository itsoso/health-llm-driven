from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _active_patterns(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_root_easignore_preserves_gitignore_and_excludes_non_mobile_payloads():
    easignore = REPO_ROOT / ".easignore"
    assert easignore.exists(), (
        "EAS archives the repository root for this monorepo, so mobile/.easignore "
        "cannot prevent unrelated repository payloads from being uploaded."
    )

    eas_patterns = _active_patterns(easignore)
    git_patterns = _active_patterns(REPO_ROOT / ".gitignore")

    assert git_patterns <= eas_patterns, (
        "The root .easignore replaces .gitignore during EAS packaging and must "
        "retain every existing ignore rule, including secret and dependency rules."
    )

    required_exclusions = {
        "/.git",
        "/.ruff_cache",
        "/.pytest_cache",
        "/.github",
        "/.agents",
        "/.cursor",
        "/htmlcov",
        "/backend",
        "/frontend",
        "/packages",
        "/docs",
        "/design",
        "/apps/mac",
        "/apps/rokid-pushup-glasses",
        "/mobile/ios",
        "/mobile/android",
        "/mobile/patches",
        "/mobile/assets/rokid",
    }
    assert required_exclusions <= eas_patterns

    assert "/apps/watch" not in eas_patterns, (
        "Watch build profiles need the repository-level apps/watch sources."
    )
