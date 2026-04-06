"""Skills API - 公开的 Skill 定义服务 + Skills Hub 管理"""
import logging
import re
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from typing import List, Dict, Any
from app.config import settings
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.skill_registry import skill_registry
from app.services.skills_hub_client import skills_hub_client

logger = logging.getLogger(__name__)

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
        "base_url": f"{settings.site_base_url}/api",
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


@router.get("/{skill_name}/install-command", response_class=PlainTextResponse)
def get_install_command(skill_name: str):
    """生成 OpenClaw 一键安装/更新命令

    在任意 OpenClaw 对话中粘贴返回的内容即可安装或更新此 Skill。
    """
    skill_file = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_file.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    content = skill_file.read_text(encoding="utf-8")
    fm = _parse_frontmatter(content)
    name = fm.get("name", skill_name)
    version = fm.get("version", "")

    return (
        f"# 安装/更新 {name} v{version}\n"
        f"# 将以下内容完整粘贴到 OpenClaw 对话中发送即可\n\n"
        f"安装技能\n{content}"
    )


# ========== Skills Hub 端点 ==========

@router.get("/hub/domains")
def list_hub_domains(
    current_user: User = Depends(get_current_user_required),
):
    """列出 Hub 的所有技能领域"""
    return {"domains": skills_hub_client.list_domains()}


@router.get("/hub/search")
def search_hub_skills(
    keyword: str = Query(..., min_length=1, description="搜索关键词"),
    current_user: User = Depends(get_current_user_required),
):
    """搜索 Hub 中的技能"""
    results = skills_hub_client.search_skills(keyword)
    return {"keyword": keyword, "results": results, "count": len(results)}


@router.post("/hub/install")
def install_hub_skill(
    domain: str = Query(..., description="技能领域"),
    skill_name: str = Query(..., description="技能名称"),
    current_user: User = Depends(get_current_user_required),
):
    """从 Hub 安装技能到本地（仅管理员）"""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="仅管理员可安装 Hub 技能")
    result = skills_hub_client.install_skill(domain, skill_name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.delete("/hub/uninstall/{skill_name}")
def uninstall_hub_skill(
    skill_name: str,
    current_user: User = Depends(get_current_user_required),
):
    """卸载从 Hub 安装的技能（仅管理员）"""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="仅管理员可卸载技能")
    result = skills_hub_client.uninstall_skill(skill_name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/hub/installed")
def list_hub_installed(
    current_user: User = Depends(get_current_user_required),
):
    """列出从 Hub 安装的技能"""
    return {"skills": skills_hub_client.list_installed_hub_skills()}


@router.get("/{skill_name}/references")
def list_skill_references(
    skill_name: str,
    current_user: User = Depends(get_current_user_required),
):
    """列出 Skill 的参考文档"""
    refs = skill_registry.list_skill_references(skill_name)
    return {"skill": skill_name, "references": refs}


@router.get("/{skill_name}/references/{ref_file}")
def get_skill_reference_content(
    skill_name: str,
    ref_file: str,
    current_user: User = Depends(get_current_user_required),
):
    """获取 Skill 的参考文档内容"""
    content = skill_registry.get_skill_reference(skill_name, ref_file)
    if content is None:
        raise HTTPException(status_code=404, detail=f"参考文档 {ref_file} 不存在")
    return {"skill": skill_name, "reference": ref_file, "content": content}
