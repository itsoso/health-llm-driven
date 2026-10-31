#!/usr/bin/env python3
"""Classify repository changes into conservative CI/release scopes."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable


RUNTIME_KEYS = (
    "run_backend",
    "run_frontend",
    "run_mobile",
    "run_mac",
    "run_type_drift",
    "run_release",
)

TOOLING_ONLY_FILES = {
    "scripts/check_agent_skill_governance.py",
    "scripts/run_tooling_pytests.py",
    "scripts/tooling_pytest_guard.py",
    "backend/tests/test_agent_skill_governance.py",
    "backend/tests/test_agent_skill_manifests.py",
    "backend/tests/test_doc_drift_narrative_counts.py",
    "backend/tests/test_doc_drift_skill_contract.py",
    "backend/tests/test_dossier_consistency.py",
    "backend/tests/test_reva_health_harness_plugin_package.py",
    "backend/tests/test_system_map_agent_context.py",
    "backend/tests/test_system_map_generator.py",
    "plugins/reva-health-harness/.codex-plugin/plugin.json",
    "plugins/reva-health-harness/README.md",
}

TOOLING_ONLY_PREFIXES = (
    ".claude/skills/health-harness-orchestrator/",
    ".claude/skills/product-pipeline/",
    ".claude/skills/reva-workflow-router/",
    "docs/governance/agent-skill-",
    "plugins/reva-health-harness/skills/health-harness-orchestrator/",
    "plugins/reva-health-harness/skills/product-pipeline/",
    "plugins/reva-health-harness/skills/reva-workflow-router/",
)

DOC_ROOT_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "MEMORY.md",
    "README.md",
    "SECURITY.md",
}

RELEASE_ONLY_FILES = {
    "deploy.sh",
    "backend/scripts/activate_health_evidence_runtime.sh",
    "backend/scripts/archive_backup_offsite.sh",
    "backend/scripts/verify_recent_offsite_backup.sh",
    "backend/scripts/backup_db.sh",
    "backend/scripts/rollback_release.sh",
    "scripts/release-preflight.sh",
    "scripts/test_backup_security.py",
    "scripts/test_deploy_script.py",
    "scripts/test_deploy_no_backup.py",
    "scripts/test_infrastructure_security.py",
    "scripts/test_release_input_digest.py",
    "scripts/test_release_lock.py",
    "scripts/test_release_rollback.py",
    "scripts/test_runtime_state_release_transaction.py",
}


def _full_result() -> dict[str, bool]:
    return {
        "docs_only": False,
        "tooling_only": False,
        "run_docs": True,
        "run_tooling": True,
        **{key: True for key in RUNTIME_KEYS},
        "release_only": False,
        "full": True,
    }


def _is_documentation(path: str) -> bool:
    return (
        path.startswith("docs/")
        or path in DOC_ROOT_FILES
        or ("/" not in path and path.endswith((".md", ".mdx", ".rst")))
    )


def _is_tooling_only(path: str) -> bool:
    return path in TOOLING_ONLY_FILES or path.startswith(TOOLING_ONLY_PREFIXES)


def _requires_full(path: str) -> bool:
    return (
        path.startswith(".github/")
        or (
            path.startswith("scripts/")
            and path not in RELEASE_ONLY_FILES
            and not _is_tooling_only(path)
        )
        or path.startswith("packages/shared/")
        or path in {"docker-compose.yml", "docker-compose.prod.yml"}
        or path.endswith(
            (
                "/requirements.lock",
                "/requirements.txt",
                "/requirements-dev.txt",
                "/package-lock.json",
                "/pnpm-lock.yaml",
                "/yarn.lock",
            )
        )
        or path in {"package.json", "pyproject.toml", "uv.lock"}
    )


def classify_changes(
    paths: Iterable[str], *, event_name: str = "local"
) -> dict[str, bool]:
    """Return fail-closed CI scopes for a normalized changed-file list."""

    normalized = sorted(
        {
            path.strip().removeprefix("./")
            for path in paths
            if path.strip()
        }
    )
    if event_name not in {"push", "pull_request", "local"} or not normalized:
        return _full_result()
    if any(_requires_full(path) for path in normalized):
        return _full_result()

    result = {
        "docs_only": True,
        "tooling_only": False,
        "run_docs": True,
        "run_tooling": False,
        **{key: False for key in RUNTIME_KEYS},
        "release_only": False,
        "full": False,
    }
    for path in normalized:
        if _is_tooling_only(path):
            result["docs_only"] = False
            result["run_tooling"] = True
            continue
        if _is_documentation(path):
            continue
        if path in RELEASE_ONLY_FILES:
            result["docs_only"] = False
            result["run_release"] = True
            continue
        result["docs_only"] = False
        if path.startswith("backend/"):
            result["run_backend"] = True
            if path.startswith(("backend/migrations/", "backend/scripts/")):
                result["run_release"] = True
            if path.startswith("backend/app/") or path == "backend/main.py":
                result["run_type_drift"] = True
        elif path.startswith("frontend/"):
            result["run_frontend"] = True
        elif path.startswith("mobile/"):
            result["run_mobile"] = True
        elif path.startswith("apps/mac/"):
            result["run_mac"] = True
        elif path.startswith(("mcp-server/", "infra/")):
            return _full_result()
        else:
            return _full_result()

    result["release_only"] = result["run_release"] and not any(
        result[key]
        for key in (
            "run_backend",
            "run_frontend",
            "run_mobile",
            "run_mac",
            "run_type_drift",
        )
    )
    result["tooling_only"] = result["run_tooling"] and not any(
        result[key] for key in RUNTIME_KEYS
    )

    # Main is the release candidate: select full coverage on its first run,
    # instead of duplicating scoped push CI with a manual full workflow.
    # Agent-governance-only changes are runtime-independent and use their
    # isolated tooling gate on both PR and main. Classifier/workflow changes
    # are deliberately outside that allowlist and therefore still run full.
    if (
        event_name == "push"
        and not result["docs_only"]
        and not result["tooling_only"]
    ):
        return _full_result()

    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--format",
        choices=("json", "github", "shell"),
        default="json",
    )
    parser.add_argument("--event-name", default="local")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = classify_changes(sys.stdin.read().splitlines(), event_name=args.event_name)
    if args.format == "json":
        print(json.dumps(result, sort_keys=True))
    else:
        for key, value in result.items():
            rendered = "true" if value else "false"
            if args.format == "shell":
                rendered = "1" if value else "0"
                print(f"{key.upper()}={rendered}")
            else:
                print(f"{key}={rendered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
