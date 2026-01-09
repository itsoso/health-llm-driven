"""
设备管理 API

提供多智能设备的绑定、同步、管理功能
支持：Garmin、华为手表、Apple Watch（未来）
"""

import os
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.device_credential import DeviceCredential
from app.services.device_adapters import DeviceManager, DeviceType

logger = logging.getLogger(__name__)

router = APIRouter()


# ===== Pydantic 模型 =====

class SupportedDevice(BaseModel):
    """支持的设备"""
    type: str
    name: str
    auth_type: str  # password, oauth2, file


class DeviceCredentialResponse(BaseModel):
    """设备凭证响应"""
    id: int
    device_type: str
    auth_type: str
    is_valid: bool
    sync_enabled: bool
    last_sync_at: Optional[str]
    last_error: Optional[str]
    config: dict
    created_at: Optional[str]


class BindPasswordDeviceRequest(BaseModel):
    """绑定账号密码设备请求（如Garmin）"""
    email: str
    password: str
    is_cn: bool = False


class OAuthCallbackRequest(BaseModel):
    """OAuth 回调请求"""
    code: str
    state: str


class SyncRequest(BaseModel):
    """同步请求"""
    days: int = 7


class DeviceSyncResult(BaseModel):
    """设备同步结果"""
    success: bool
    device: str
    synced_days: int = 0
    failed_days: int = 0
    message: str


# ===== API 端点 =====

@router.get("/supported", response_model=List[SupportedDevice], summary="获取支持的设备列表")
async def get_supported_devices():
    """
    获取系统支持的所有智能设备类型
    
    返回设备类型、名称和认证方式
    """
    return DeviceManager.get_supported_devices()


@router.get("/me", response_model=List[DeviceCredentialResponse], summary="获取我绑定的设备")
async def get_my_devices(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户绑定的所有设备"""
    credentials = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id
    ).all()
    
    return [cred.to_response_dict() for cred in credentials]


@router.get("/me/{device_type}", response_model=DeviceCredentialResponse, summary="获取指定设备凭证")
async def get_device_credential(
    device_type: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取指定类型设备的凭证信息"""
    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id,
        DeviceCredential.device_type == device_type
    ).first()
    
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未绑定 {device_type} 设备"
        )
    
    return credential.to_response_dict()


# ===== 华为手表 OAuth 流程 =====

@router.get("/huawei/oauth/authorize", summary="获取华为授权URL")
async def get_huawei_oauth_url(
    redirect_uri: str = Query(..., description="授权后的回调地址"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取华为 OAuth 授权 URL
    
    用户访问返回的 URL 后会跳转到华为登录页面，
    授权完成后华为会重定向到 redirect_uri 并带上 code 参数
    """
    from app.services.device_adapters.huawei import HuaweiHealthAdapter
    
    # 生成 state 参数（包含用户ID，用于回调时识别用户）
    state = f"{current_user.id}:{secrets.token_urlsafe(16)}"
    
    # 保存 state 到数据库或缓存（简单起见这里用数据库）
    # 实际生产环境建议用 Redis
    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id,
        DeviceCredential.device_type == "huawei"
    ).first()
    
    if not credential:
        credential = DeviceCredential(
            user_id=current_user.id,
            device_type="huawei",
            auth_type="oauth2",
            is_valid=False
        )
        db.add(credential)
    
    # 保存 state 到 config
    credential.set_config({"oauth_state": state, "redirect_uri": redirect_uri})
    db.commit()
    
    # 创建适配器获取授权 URL
    adapter = HuaweiHealthAdapter()
    auth_url = adapter.get_oauth_url(redirect_uri, state)
    
    return {
        "auth_url": auth_url,
        "state": state,
        "message": "请访问 auth_url 完成授权"
    }


@router.post("/huawei/oauth/callback", summary="华为OAuth回调处理")
async def huawei_oauth_callback(
    request: OAuthCallbackRequest,
    db: Session = Depends(get_db)
):
    """
    处理华为 OAuth 回调
    
    当用户在华为页面完成授权后，华为会重定向到回调地址并带上 code，
    前端将 code 和 state 提交到此接口完成绑定
    """
    from app.services.device_adapters.huawei import HuaweiHealthAdapter
    
    # 从 state 中解析用户 ID
    try:
        user_id_str, _ = request.state.split(":", 1)
        user_id = int(user_id_str)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的 state 参数"
        )
    
    # 查找凭证记录
    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == user_id,
        DeviceCredential.device_type == "huawei"
    ).first()
    
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到对应的授权请求"
        )
    
    # 验证 state
    config = credential.get_config()
    if config.get("oauth_state") != request.state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="state 验证失败，可能存在 CSRF 攻击"
        )
    
    # 用 code 换取 token
    try:
        adapter = HuaweiHealthAdapter()
        token_result = await adapter.exchange_code_for_token(
            request.code, 
            config.get("redirect_uri", "")
        )
        
        # 保存 token
        expires_at = datetime.now() + timedelta(seconds=token_result.get("expires_in", 3600))
        credential.set_oauth_tokens(
            access_token=token_result["access_token"],
            refresh_token=token_result.get("refresh_token"),
            expires_at=expires_at,
            scope=token_result.get("scope")
        )
        credential.mark_valid()
        credential.update_sync_time()
        
        # 清理临时 state
        config.pop("oauth_state", None)
        credential.set_config(config)
        
        db.commit()
        
        return {
            "success": True,
            "message": "华为手表绑定成功！",
            "device_type": "huawei"
        }
        
    except Exception as e:
        logger.error(f"华为 OAuth 回调处理失败: {e}")
        credential.mark_invalid(str(e))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"授权失败: {str(e)}"
        )


@router.post("/huawei/test-connection", summary="测试华为连接")
async def test_huawei_connection(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """测试华为手表连接是否正常"""
    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id,
        DeviceCredential.device_type == "huawei"
    ).first()
    
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未绑定华为手表"
        )
    
    try:
        adapter = DeviceManager.create_adapter_from_credential(credential)
        result = await adapter.test_connection()
        
        if result["success"]:
            credential.mark_valid()
        else:
            credential.mark_invalid(result.get("message"))
        db.commit()
        
        return result
        
    except Exception as e:
        credential.mark_invalid(str(e))
        db.commit()
        return {"success": False, "message": str(e)}


@router.post("/huawei/sync", response_model=DeviceSyncResult, summary="同步华为数据")
async def sync_huawei_data(
    request: SyncRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """同步华为手表数据"""
    result = await DeviceManager.sync_device_data(
        db, 
        current_user.id, 
        "huawei", 
        request.days
    )
    return DeviceSyncResult(
        success=result["success"],
        device="huawei",
        synced_days=result.get("synced_days", 0),
        failed_days=result.get("failed_days", 0),
        message=result["message"]
    )


@router.delete("/huawei", summary="解绑华为手表")
async def unbind_huawei(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """解除华为手表绑定"""
    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id,
        DeviceCredential.device_type == "huawei"
    ).first()
    
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未绑定华为手表"
        )
    
    db.delete(credential)
    db.commit()
    
    return {"success": True, "message": "华为手表已解绑"}


# ===== 通用设备操作 =====

@router.post("/{device_type}/sync", response_model=DeviceSyncResult, summary="同步指定设备数据")
async def sync_device(
    device_type: str,
    request: SyncRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """同步指定类型设备的数据"""
    if not DeviceManager.is_supported(device_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的设备类型: {device_type}"
        )
    
    result = await DeviceManager.sync_device_data(
        db,
        current_user.id,
        device_type,
        request.days
    )
    
    return DeviceSyncResult(
        success=result["success"],
        device=device_type,
        synced_days=result.get("synced_days", 0),
        failed_days=result.get("failed_days", 0),
        message=result["message"]
    )


@router.post("/sync-all", summary="同步所有设备数据")
async def sync_all_devices(
    request: SyncRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """同步用户绑定的所有设备数据"""
    results = await DeviceManager.sync_all_devices(
        db,
        current_user.id,
        request.days
    )
    
    return {
        "success": True,
        "results": results,
        "message": f"已同步 {len(results)} 个设备"
    }


@router.put("/{device_type}/toggle-sync", summary="启用/禁用设备同步")
async def toggle_device_sync(
    device_type: str,
    enabled: bool = Query(..., description="是否启用同步"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """启用或禁用指定设备的自动同步"""
    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id,
        DeviceCredential.device_type == device_type
    ).first()
    
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未绑定 {device_type} 设备"
        )
    
    credential.sync_enabled = enabled
    db.commit()
    
    return {
        "success": True,
        "message": f"已{'启用' if enabled else '禁用'} {device_type} 同步",
        "sync_enabled": enabled
    }


@router.delete("/{device_type}", summary="解绑设备")
async def unbind_device(
    device_type: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """解除指定设备的绑定"""
    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id,
        DeviceCredential.device_type == device_type
    ).first()
    
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未绑定 {device_type} 设备"
        )
    
    db.delete(credential)
    db.commit()
    
    return {"success": True, "message": f"{device_type} 设备已解绑"}
