"""Runtime Agent skill manifest guardrails."""
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
BASH_BLOCK = re.compile(r"```bash\n(.*?)```", re.DOTALL)


def _single_quoted_substitution_lines(script: str) -> list[str]:
    """Lines where `$(` sits inside single quotes, so the shell sends it literally."""
    offenders = []
    quote = None  # shell quotes may span lines
    for line in script.splitlines():
        index, hit = 0, False
        while index < len(line):
            char = line[index]
            if quote == "'":
                if char == "'":
                    quote = None
                elif line.startswith("$(", index):
                    hit = True
            elif char == "\\":
                index += 1
            elif quote == '"':
                if char == '"':
                    quote = None
            elif char in "'\"":
                quote = char
            elif char == "#" and (index == 0 or line[index - 1].isspace()):
                break
            index += 1
        if hit:
            offenders.append(line.strip())
    return offenders


def test_runtime_skills_do_not_advertise_openclaw_metadata():
    offenders = []
    for skill_path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        content = skill_path.read_text(encoding="utf-8")
        if "\n  openclaw:" in content or "\nopenclaw:" in content:
            offenders.append(skill_path.relative_to(ROOT).as_posix())

    assert offenders == []


def test_runtime_skill_bash_examples_do_not_single_quote_command_substitution():
    offenders = []
    for skill_path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        content = skill_path.read_text(encoding="utf-8")
        for block in BASH_BLOCK.findall(content):
            for line in _single_quoted_substitution_lines(block):
                offenders.append(f"{skill_path.relative_to(ROOT).as_posix()}: {line}")

    assert offenders == []
