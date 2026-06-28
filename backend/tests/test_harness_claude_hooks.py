from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _assert_tracked(path: str) -> None:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, f"{path} must be tracked so harness hooks are portable"


def test_claude_hooks_are_versioned_and_wired():
    for path in [
        ".claude/settings.json",
        ".claude/hooks/session-start-bootstrap.sh",
        ".claude/hooks/doc-drift-precommit.sh",
    ]:
        _assert_tracked(path)

    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))

    session_hooks = settings["hooks"]["SessionStart"][0]["hooks"]
    assert session_hooks == [
        {
            "type": "command",
            "command": 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/session-start-bootstrap.sh"',
        }
    ]

    pre_tool = settings["hooks"]["PreToolUse"][0]
    assert pre_tool["matcher"] == "Bash"
    assert pre_tool["hooks"] == [
        {
            "type": "command",
            "command": 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/doc-drift-precommit.sh"',
        }
    ]


def test_session_start_hook_injects_core_harness_invariants():
    text = (ROOT / ".claude" / "hooks" / "session-start-bootstrap.sh").read_text(encoding="utf-8")

    assert "docs/system-map/INDEX.md" in text
    assert "docs/_generated/system-map.json" in text
    assert "R4" in text
    assert "fail-closed + fail-loud" in text
    assert "AGENTS.md" in text


def test_commit_hook_runs_doc_drift_and_dossier_gates_only_for_commits():
    text = (ROOT / ".claude" / "hooks" / "doc-drift-precommit.sh").read_text(encoding="utf-8")

    assert "scripts/check_doc_drift.py" in text
    assert "backend/scripts/check_dossier_consistency.py" in text
    assert "SKIP_DOC_DRIFT_HOOK" in text
    assert "git[[:space:]]+commit" in text
    assert "grep -q \"git commit\"" in text
