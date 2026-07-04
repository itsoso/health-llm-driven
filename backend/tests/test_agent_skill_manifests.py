"""Runtime Agent skill manifest guardrails."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"


def test_runtime_skills_do_not_advertise_openclaw_metadata():
    offenders = []
    for skill_path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        content = skill_path.read_text(encoding="utf-8")
        if "\n  openclaw:" in content or "\nopenclaw:" in content:
            offenders.append(skill_path.relative_to(ROOT).as_posix())

    assert offenders == []
