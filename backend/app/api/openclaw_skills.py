"""OpenClaw Skills 管理 API — 管理员通过 SSH 远程管理 OpenClaw 服务器上的 Skills"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user_required
from app.models.user import User
from app.services.openclaw_skills_service import openclaw_skills_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/openclaw/skills", tags=["openclaw-skills"])


# ── Schemas ───────────────────────────────────────────────

class SkillCreateRequest(BaseModel):
    name: str
    skill_md_content: str
    enabled: bool = True
    env: Optional[dict] = None
    api_key: Optional[str] = None


class SkillToggleRequest(BaseModel):
    enabled: bool


class ClawHubSearchRequest(BaseModel):
    query: str


class ClawHubInstallRequest(BaseModel):
    slug: str


# ── 权限检查 ─────────────────────────────────────────────

def _require_admin(user: User):
    """要求管理员权限"""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")


# ── Endpoints (固定路径优先于参数路径) ─────────────────────

@router.get("/gateway/status", summary="OpenClaw Gateway 状态")
async def gateway_status(
    current_user: User = Depends(get_current_user_required),
):
    _require_admin(current_user)
    try:
        return openclaw_skills_service.get_gateway_status()
    except Exception as e:
        logger.error(f"获取 Gateway 状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"连接失败: {e}")


@router.post("/gateway/restart", summary="重启 OpenClaw Gateway")
async def restart_gateway(
    current_user: User = Depends(get_current_user_required),
):
    _require_admin(current_user)
    try:
        result = openclaw_skills_service.restart_gateway()
        return {"ok": True, "message": result}
    except Exception as e:
        logger.error(f"重启 Gateway 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"重启失败: {e}")


@router.post("/clawhub/search", summary="搜索 ClawHub 公共 Skills")
async def clawhub_search(
    req: ClawHubSearchRequest,
    current_user: User = Depends(get_current_user_required),
):
    _require_admin(current_user)
    try:
        result = openclaw_skills_service.clawhub_search(req.query)
        return {"query": req.query, "result": result}
    except Exception as e:
        logger.error(f"ClawHub 搜索失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"搜索失败: {e}")


@router.post("/clawhub/install", summary="从 ClawHub 安装 Skill")
async def clawhub_install(
    req: ClawHubInstallRequest,
    current_user: User = Depends(get_current_user_required),
):
    _require_admin(current_user)
    try:
        result = openclaw_skills_service.clawhub_install(req.slug)
        return {"slug": req.slug, "result": result}
    except Exception as e:
        logger.error(f"ClawHub 安装失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"安装失败: {e}")


# ── Skills CRUD ──────────────────────────────────────────

@router.get("", summary="列出所有 Skills")
async def list_skills(
    current_user: User = Depends(get_current_user_required),
):
    _require_admin(current_user)
    try:
        return openclaw_skills_service.list_skills()
    except Exception as e:
        logger.error(f"列出 Skills 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"连接 OpenClaw 服务器失败: {e}")


@router.post("", summary="创建或更新 Skill")
async def create_or_update_skill(
    req: SkillCreateRequest,
    current_user: User = Depends(get_current_user_required),
):
    _require_admin(current_user)
    if not req.name or not req.skill_md_content:
        raise HTTPException(status_code=400, detail="name 和 skill_md_content 不能为空")
    try:
        result = openclaw_skills_service.create_or_update_skill(
            name=req.name,
            skill_md_content=req.skill_md_content,
            enabled=req.enabled,
            env=req.env,
            api_key=req.api_key,
        )
        return result
    except Exception as e:
        logger.error(f"创建/更新 Skill 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"操作失败: {e}")


@router.get("/{name}", summary="获取 Skill 详情")
async def get_skill(
    name: str,
    current_user: User = Depends(get_current_user_required),
):
    _require_admin(current_user)
    try:
        skill = openclaw_skills_service.get_skill(name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' 不存在")
        return skill
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 Skill 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"连接 OpenClaw 服务器失败: {e}")


@router.delete("/{name}", summary="删除 Skill")
async def delete_skill(
    name: str,
    current_user: User = Depends(get_current_user_required),
):
    _require_admin(current_user)
    try:
        ok = openclaw_skills_service.delete_skill(name)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' 不存在")
        return {"ok": True, "message": f"已删除 Skill '{name}'"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除 Skill 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"操作失败: {e}")


@router.put("/{name}/toggle", summary="启用/禁用 Skill")
async def toggle_skill(
    name: str,
    req: SkillToggleRequest,
    current_user: User = Depends(get_current_user_required),
):
    _require_admin(current_user)
    try:
        ok = openclaw_skills_service.toggle_skill(name, req.enabled)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' 配置不存在")
        return {"ok": True, "name": name, "enabled": req.enabled}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换 Skill 状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"操作失败: {e}")
