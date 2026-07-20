"""系统监控和性能 API"""
import os
import time
from datetime import datetime

# psutil 可选导入，某些环境可能没有安装
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
from app.api.users import get_current_user_required
from app.models.user import User
from app.utils.logging_config import log_manager
from app.utils.timezone import CHINA_TIMEZONE

router = APIRouter()


class AgentRuntimeRolloutCircuitResponse(BaseModel):
    status: Literal["active", "paused"]
    reason_code: str | None = None
    version: int
    last_evaluated_at: datetime | None = None


class AgentRuntimeRolloutThresholdsResponse(BaseModel):
    window_minutes: int
    min_terminal_runs: int
    failure_rate_percent: int
    reconciliation_runs: int
    stale_active_runs: int


class AgentRuntimeRolloutDurationResponse(BaseModel):
    p50: int | None = None
    p95: int | None = None


class AgentRuntimeRolloutSnapshotResponse(BaseModel):
    window_started_at: datetime
    evaluated_at: datetime
    terminal_runs: int
    failed_runs: int
    reconciliation_runs: int
    stale_active_runs: int
    status_counts: dict[str, int]
    tool_status_counts: dict[str, int]
    duration_ms: AgentRuntimeRolloutDurationResponse


class AgentRuntimeRolloutStatusResponse(BaseModel):
    mode: Literal["off", "canary", "enforce"]
    canary_percent: int
    allowlist_count: int
    circuit: AgentRuntimeRolloutCircuitResponse
    thresholds: AgentRuntimeRolloutThresholdsResponse
    snapshot: AgentRuntimeRolloutSnapshotResponse


class AgentRuntimeRolloutTransitionResponse(BaseModel):
    changed: bool
    status: Literal["active", "paused"]
    reason_code: str | None = None


def _require_admin(current_user: User) -> None:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")


@router.get("/health")
async def health_check():
    """基础健康检查"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(CHINA_TIMEZONE).isoformat(),
        "version": "1.0.0"
    }


@router.get("/status")
async def system_status(
    current_user: User = Depends(get_current_user_required)
):
    """获取系统状态 (需要登录)"""
    if not PSUTIL_AVAILABLE:
        return {
            "timestamp": datetime.now(CHINA_TIMEZONE).isoformat(),
            "error": "psutil 模块不可用，无法获取系统状态",
            "system": None,
            "process": None
        }

    # CPU 和内存
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    # 进程信息
    process = psutil.Process()
    process_memory = process.memory_info()

    return {
        "timestamp": datetime.now(CHINA_TIMEZONE).isoformat(),
        "system": {
            "cpu_percent": cpu_percent,
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "percent": memory.percent
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "percent": disk.percent
            }
        },
        "process": {
            "memory_mb": round(process_memory.rss / (1024**2), 2),
            "cpu_percent": process.cpu_percent()
        }
    }


@router.get("/logs")
async def log_status(
    current_user: User = Depends(get_current_user_required)
):
    """获取日志配置状态"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    return {
        "status": log_manager.get_status(),
        "env_log_level": os.getenv('LOG_LEVEL', 'INFO'),
        "env_debug": os.getenv('DEBUG', 'false')
    }


@router.post("/logs/level")
async def set_log_level(
    level: str,
    logger_name: Optional[str] = None,
    current_user: User = Depends(get_current_user_required)
):
    """动态设置日志级别 (需要管理员权限)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    import logging
    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL,
    }

    level_upper = level.upper()
    if level_upper not in level_map:
        raise HTTPException(status_code=400, detail=f"无效的日志级别: {level}")

    log_manager.set_level(level_map[level_upper], logger_name)

    return {
        "success": True,
        "message": f"日志级别已设置为 {level_upper}",
        "status": log_manager.get_status()
    }


@router.post("/logs/debug")
async def toggle_debug_mode(
    enable: bool,
    current_user: User = Depends(get_current_user_required)
):
    """切换调试模式"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    if enable:
        log_manager.enable_debug()
    else:
        log_manager.disable_debug()

    return {
        "success": True,
        "debug_mode": enable,
        "status": log_manager.get_status()
    }


@router.get("/db")
async def database_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """数据库状态检查"""
    try:
        start = time.time()
        db.execute(text("SELECT 1"))
        query_time = (time.time() - start) * 1000

        return {
            "status": "connected",
            "query_time_ms": round(query_time, 2),
            "timestamp": datetime.now(CHINA_TIMEZONE).isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now(CHINA_TIMEZONE).isoformat()
        }


@router.get("/metrics")
async def get_metrics(
    current_user: User = Depends(get_current_user_required)
):
    """获取简单性能指标"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    if not PSUTIL_AVAILABLE:
        return {
            "timestamp": datetime.now(CHINA_TIMEZONE).isoformat(),
            "error": "psutil 模块不可用，无法获取性能指标",
            "load_avg": os.getloadavg() if hasattr(os, 'getloadavg') else None
        }

    # 系统运行时间
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time

    # 网络统计
    net_io = psutil.net_io_counters()

    return {
        "timestamp": datetime.now(CHINA_TIMEZONE).isoformat(),
        "uptime_hours": round(uptime.total_seconds() / 3600, 2),
        "network": {
            "bytes_sent_mb": round(net_io.bytes_sent / (1024**2), 2),
            "bytes_recv_mb": round(net_io.bytes_recv / (1024**2), 2)
        },
        "cpu_count": psutil.cpu_count(),
        "load_avg": os.getloadavg() if hasattr(os, 'getloadavg') else None
    }


@router.get(
    "/agent-runtime/rollout",
    response_model=AgentRuntimeRolloutStatusResponse,
)
async def get_agent_runtime_rollout(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Return aggregate-only Runtime rollout health for administrators."""
    from app.services.agent_runtime_rollout import (
        AgentRuntimeRolloutService,
        rollout_public_configuration,
    )

    _require_admin(current_user)
    rollout = AgentRuntimeRolloutService(db)
    config = rollout_public_configuration()
    state = rollout.get_state()
    snapshot = rollout.snapshot(window_minutes=int(config["window_minutes"]))
    return {
        "mode": config["mode"],
        "canary_percent": config["canary_percent"],
        "allowlist_count": config["allowlist_count"],
        "circuit": {
            "status": state.status,
            "reason_code": state.reason_code,
            "version": state.version,
            "last_evaluated_at": state.last_evaluated_at,
        },
        "thresholds": {
            "window_minutes": config["window_minutes"],
            "min_terminal_runs": config["min_terminal_runs"],
            "failure_rate_percent": config["failure_rate_percent"],
            "reconciliation_runs": 1,
            "stale_active_runs": 1,
        },
        "snapshot": snapshot.to_dict(),
    }


@router.post(
    "/agent-runtime/pause",
    response_model=AgentRuntimeRolloutTransitionResponse,
)
async def pause_agent_runtime_rollout(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Idempotently stop future managed admission; existing Runs remain operable."""
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    _require_admin(current_user)
    result = AgentRuntimeRolloutService(db).pause(
        actor_kind="admin",
        reason_code="manual_pause",
        actor_user_id=current_user.id,
    )
    return {
        "changed": result.changed,
        "status": result.status,
        "reason_code": result.reason_code,
    }


@router.post(
    "/agent-runtime/resume",
    response_model=AgentRuntimeRolloutTransitionResponse,
)
async def resume_agent_runtime_rollout(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Idempotently resume future managed admission after operator review."""
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    _require_admin(current_user)
    result = AgentRuntimeRolloutService(db).resume(
        actor_user_id=current_user.id,
    )
    return {
        "changed": result.changed,
        "status": result.status,
        "reason_code": result.reason_code,
    }
