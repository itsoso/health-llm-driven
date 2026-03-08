"""Skills API - 公开的 Skill 定义服务"""
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from typing import List, Dict, Any

router = APIRouter()

SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


def _parse_frontmatter(content: str) -> Dict[str, Any]:
    """解析 SKILL.md 的 YAML frontmatter"""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).split('\n'):
        line = line.strip()
        if ':' in line and not line.startswith('-') and not line.startswith('#'):
            key, _, val = line.partition(':')
            key = key.strip()
            val = val.strip()
            if val:
                fm[key] = val
    return fm


def _get_body(content: str) -> str:
    """获取 frontmatter 之后的正文"""
    match = re.match(r'^---\s*\n.*?\n---\s*\n', content, re.DOTALL)
    if match:
        return content[match.end():]
    return content


@router.get("", response_model=List[Dict[str, Any]])
def list_skills():
    """列出所有可用的 Skills"""
    skills = []
    if not SKILLS_DIR.exists():
        return skills

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        content = skill_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(content)
        skills.append({
            "name": fm.get("name", skill_dir.name),
            "description": fm.get("description", ""),
            "version": fm.get("version", "1.0.0"),
            "slug": skill_dir.name,
        })
    return skills


@router.get("/manifest.json", summary="Skills 打包清单（一键安装/更新）")
def get_skills_manifest():
    """返回所有 Skills 的打包 JSON，供 OpenClaw 一键安装或更新"""
    skills = []
    if not SKILLS_DIR.exists():
        return {"version": "1.0", "skills": skills}

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        content = skill_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(content)
        body = _get_body(content)
        skills.append({
            "name": fm.get("name", skill_dir.name),
            "slug": skill_dir.name,
            "description": fm.get("description", ""),
            "version": fm.get("version", "1.0.0"),
            "content": body.strip(),
            "raw_url": f"/api/v1/skills/{skill_dir.name}/raw",
        })

    return {
        "version": "1.0",
        "base_url": "https://health.executor.life/api",
        "auth_type": "Bearer Token",
        "skills": skills,
    }


@router.get("/{skill_name}")
def get_skill(skill_name: str):
    """获取 Skill 详情（结构化 JSON）"""
    skill_file = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_file.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    content = skill_file.read_text(encoding="utf-8")
    fm = _parse_frontmatter(content)
    body = _get_body(content)

    return {
        "name": fm.get("name", skill_name),
        "description": fm.get("description", ""),
        "version": fm.get("version", "1.0.0"),
        "slug": skill_name,
        "content": body.strip(),
        "raw_url": f"/api/v1/skills/{skill_name}/raw",
    }


@router.get("/{skill_name}/raw", response_class=PlainTextResponse)
def get_skill_raw(skill_name: str):
    """获取 Skill 原始 SKILL.md 内容（供 OpenClaw 直接安装）"""
    skill_file = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_file.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    return skill_file.read_text(encoding="utf-8")
