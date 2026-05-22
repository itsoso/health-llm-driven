from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_deploy_script_uses_root_env_as_single_source():
    deploy_script = (REPO_ROOT / "deploy.sh").read_text()

    assert 'ENV_FILE="$SCRIPT_DIR/.env"' in deploy_script
    assert ".env-online" not in deploy_script


def test_operator_docs_do_not_point_deploys_at_env_online():
    docs = "\n".join(
        [
            (REPO_ROOT / "AGENTS.md").read_text(),
            (REPO_ROOT / "CLAUDE.md").read_text(),
        ]
    )

    assert ".env-online" not in docs


def test_gitignore_only_ignores_root_env_file():
    gitignore = (REPO_ROOT / ".gitignore").read_text().splitlines()

    assert ".env" in gitignore
    assert ".env-online" not in gitignore
