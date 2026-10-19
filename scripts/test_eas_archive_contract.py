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
        "/mobile/assets/rokid",
    }
    assert required_exclusions <= eas_patterns

    assert "/mobile/patches" not in eas_patterns, "Required postinstall security patches must ship"
    assert "/mobile/patches/expo-modules-autolinking+55.0.24.patch" in eas_patterns

    assert "/apps/watch" not in eas_patterns, (
        "Watch build profiles need the repository-level apps/watch sources."
    )


def test_production_ios_pins_toolchain_instead_of_sdk55_crashing_auto_image():
    import json

    config = json.loads((REPO_ROOT / 'mobile/eas.json').read_text())
    production = config['build']['production']
    # SDK 55 auto selects Xcode 26.2: the real Store archive crashed in
    # Swift SendNonSendable while compiling ExpoModulesCore.SharedObject.emit.
    # Match the successful local Xcode 26.6 archive without weakening checks.
    assert production['ios']['image'] == 'macos-tahoe-26.5-xcode-26.6'
    assert production['node'] == '22.13.0'
    assert production['ios']['autoIncrement'] is True
