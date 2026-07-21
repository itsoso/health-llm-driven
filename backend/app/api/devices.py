"""
设备管理 API

提供多智能设备的绑定、同步、管理功能
支持：Garmin、华为手表、Apple Watch（未来）
"""

import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.device_credential import DeviceCredential
from app.services.device_adapters import DeviceManager, DeviceType

logger = logging.getLogger(__name__)

router = APIRouter()


def _invalidate_twin(user_id: int) -> None:
    """Fail-soft twin-cache invalidation after a passive health-data sync/import.

    rank7: also drops any pre-generated starter answers so they can't serve on
    freshly-synced data. A Redis error must never fail the sync endpoint.
    """
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(user_id)
    except Exception:  # noqa: BLE001
        pass


@router.get("/compare", summary="双设备一致性对比(如 Apple Watch + Garmin 同指标)")
def compare_devices(
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """同时戴多台穿戴时,同指标(HRV/静息心率/睡眠/VO2max/SpO2/步数)并排对比 + 一致度。"""
    from app.services.device_comparison_service import device_comparison

    return device_comparison(db, current_user.id, days=days)


@router.get("/sources/summary", summary="每数据源覆盖天数 + 最近一天指标快照")
def sources_summary_endpoint(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """近 days 天,按 data_source 分组:覆盖天数 / 最新日期 / 最近一天同日指标。

    客户端用此区分「记录来自哪个设备」并展示每源的数据量。
    """
    from app.services.device_comparison_service import sources_summary

    return sources_summary(db, current_user.id, days=days)


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


@router.get("/me/{device_type}", response_model=Optional[DeviceCredentialResponse], summary="获取指定设备凭证")
async def get_device_credential(
    device_type: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取指定类型设备的凭证信息

    如果未绑定设备，返回 null 而不是 404 错误
    """
    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id,
        DeviceCredential.device_type == device_type
    ).first()

    if not credential:
        return None

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


@router.get("/huawei/oauth/callback", summary="华为OAuth回调（GET重定向）")
async def huawei_oauth_callback_get(
    code: str = Query(..., description="授权码"),
    state: str = Query(..., description="状态参数"),
    db: Session = Depends(get_db)
):
    """
    处理华为 OAuth GET 重定向回调

    华为授权完成后会重定向到此接口，带上 code 和 state 参数。
    处理完成后返回 HTML 页面提示用户返回小程序。
    """
    from app.services.device_adapters.huawei import HuaweiHealthAdapter
    from fastapi.responses import HTMLResponse

    # 从 state 中解析用户 ID
    try:
        user_id_str, _ = state.split(":", 1)
        user_id = int(user_id_str)
    except Exception:
        return HTMLResponse(content="""
        <html>
        <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
        <body style="font-family: -apple-system, sans-serif; padding: 40px; text-align: center;">
            <h2 style="color: #ef4444;">❌ 授权失败</h2>
            <p>无效的授权参数，请返回小程序重试</p>
        </body>
        </html>
        """, status_code=400)

    # 查找凭证记录
    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == user_id,
        DeviceCredential.device_type == "huawei"
    ).first()

    if not credential:
        return HTMLResponse(content="""
        <html>
        <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
        <body style="font-family: -apple-system, sans-serif; padding: 40px; text-align: center;">
            <h2 style="color: #ef4444;">❌ 授权失败</h2>
            <p>未找到对应的授权请求，请返回小程序重试</p>
        </body>
        </html>
        """, status_code=404)

    # 验证 state
    config = credential.get_config()
    if config.get("oauth_state") != state:
        return HTMLResponse(content="""
        <html>
        <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
        <body style="font-family: -apple-system, sans-serif; padding: 40px; text-align: center;">
            <h2 style="color: #ef4444;">❌ 授权失败</h2>
            <p>授权验证失败，请返回小程序重试</p>
        </body>
        </html>
        """, status_code=400)

    # 用 code 换取 token
    try:
        adapter = HuaweiHealthAdapter()
        token_result = await adapter.exchange_code_for_token(
            code,
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

        return HTMLResponse(content="""
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>授权成功</title>
        </head>
        <body style="font-family: -apple-system, sans-serif; padding: 40px; text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; margin: 0;">
            <div style="background: white; border-radius: 16px; padding: 40px; max-width: 320px; margin: 0 auto; box-shadow: 0 10px 40px rgba(0,0,0,0.2);">
                <div style="font-size: 64px; margin-bottom: 20px;">✅</div>
                <h2 style="color: #10b981; margin: 0 0 16px 0;">华为手表绑定成功！</h2>
                <p style="color: #6b7280; margin: 0 0 24px 0;">您现在可以关闭此页面，返回小程序刷新查看</p>
                <div style="background: #f3f4f6; border-radius: 8px; padding: 16px;">
                    <p style="color: #374151; margin: 0; font-size: 14px;">💡 小提示：返回小程序后下拉刷新页面即可看到绑定状态</p>
                </div>
            </div>
        </body>
        </html>
        """)

    except Exception as e:
        logger.error(f"华为 OAuth 回调处理失败: {e}")
        credential.mark_invalid(str(e))
        db.commit()
        return HTMLResponse(content=f"""
        <html>
        <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
        <body style="font-family: -apple-system, sans-serif; padding: 40px; text-align: center;">
            <h2 style="color: #ef4444;">❌ 授权失败</h2>
            <p>{str(e)}</p>
            <p>请返回小程序重试</p>
        </body>
        </html>
        """, status_code=400)


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
    if result.get("success"):
        _invalidate_twin(current_user.id)
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
    if result.get("success"):
        _invalidate_twin(current_user.id)

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
    if results:
        _invalidate_twin(current_user.id)

    # 诚实性: 每个设备的 result 各带自己的 success。无条件 success=True + "已同步 N 个"
    # 会把鉴权失败的设备也计入"已同步"。按实际成功设备数派生。
    ok = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    message = f"同步完成：{len(ok)}/{len(results)} 个设备成功"
    if failed:
        failed_types = ", ".join(str(r.get("device", "unknown")) for r in failed)
        message += f"（失败: {failed_types}）"

    return {
        "success": (len(results) == 0) or len(ok) > 0,
        "results": results,
        "message": message,
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


# ===== Apple Health 文件导入 =====

@router.post("/apple/import", summary="导入 Apple Health 数据")
async def import_apple_health(
    file: UploadFile = File(..., description="Apple Health 导出的 XML 文件"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    导入 Apple Health 导出的 XML 文件

    使用步骤：
    1. 在 iPhone 上打开"健康" App
    2. 点击右上角头像 → "导出健康数据"
    3. 等待导出完成后，将 XML 文件上传到此接口

    注意：文件可能很大（几十MB），请耐心等待处理
    """
    from app.services.device_adapters.apple import AppleHealthAdapter
    from app.services.secure_upload import UploadTooLarge, read_upload_limited
    import json

    # 检查文件类型
    if not file.filename.endswith('.xml'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请上传 XML 格式的 Apple Health 导出文件"
        )

    try:
        # 读取文件内容
        try:
            content = await read_upload_limited(
                file,
                max_bytes=AppleHealthAdapter.MAX_XML_CHARS,
                chunk_size=1024 * 1024,
            )
        except UploadTooLarge as exc:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Apple Health XML 文件过大",
            ) from exc
        xml_content = content.decode('utf-8')

        # 解析 XML
        logger.info(f"开始解析 Apple Health XML 文件 (用户 {current_user.id})")
        parsed_data = AppleHealthAdapter.parse_health_xml(xml_content)

        if not parsed_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="XML 文件中未找到有效的健康数据"
            )

        # 保存到设备凭证（Apple 使用文件导入，不需要传统凭证）
        credential = db.query(DeviceCredential).filter(
            DeviceCredential.user_id == current_user.id,
            DeviceCredential.device_type == "apple"
        ).first()

        if not credential:
            credential = DeviceCredential(
                user_id=current_user.id,
                device_type="apple",
                auth_type="file",
                is_valid=True
            )
            db.add(credential)

        # 将解析的数据保存到 config（实际生产环境建议存到数据库表）
        credential.set_config({
            "imported_data": parsed_data,
            "imported_at": datetime.now().isoformat(),
            "data_days": len(parsed_data),
            "data_range": {
                "start": min(parsed_data.keys()) if parsed_data else None,
                "end": max(parsed_data.keys()) if parsed_data else None
            }
        })
        credential.mark_valid()
        credential.update_sync_time()
        db.commit()

        # 创建适配器并保存数据到数据库
        adapter = AppleHealthAdapter(imported_data=parsed_data)

        # 同步所有日期的数据
        synced = 0
        failed = 0
        for date_str in parsed_data.keys():
            try:
                from datetime import date as date_class
                target_date = date_class.fromisoformat(date_str)
                data = await adapter.fetch_daily_data(target_date)
                if data:
                    DeviceManager._save_health_data(db, current_user.id, data)
                    synced += 1
            except Exception as e:
                logger.warning(f"导入 {date_str} 数据失败: {e}")
                failed += 1

        db.commit()
        _invalidate_twin(current_user.id)

        # 诚实性: 按实际落库天数派生 success。逐日 try/except 累加, synced=0 时无一天落库
        # (全失败, 或 `if data:` 全跳过空数据日), 无条件 "导入成功：0 天" 是谎报。
        import_ok = synced > 0
        if import_ok:
            message = f"导入成功：{synced} 天数据已导入，{failed} 天失败"
        else:
            message = f"导入失败：0 天成功，{failed} 天失败（数据未落库）"

        return {
            "success": import_ok,
            "message": message,
            "data_days": len(parsed_data),
            "synced_days": synced,
            "failed_days": failed,
            "data_range": {
                "start": min(parsed_data.keys()) if parsed_data else None,
                "end": max(parsed_data.keys()) if parsed_data else None
            }
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"XML 解析失败: {str(e)}"
        )
    except Exception as e:
        logger.error(f"导入 Apple Health 数据失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导入失败: {str(e)}"
        )


@router.post("/apple/test-connection", summary="测试 Apple Health 连接")
async def test_apple_connection(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """测试 Apple Health 数据是否已导入"""
    from app.services.device_adapters.apple import AppleHealthAdapter

    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id,
        DeviceCredential.device_type == "apple"
    ).first()

    if not credential:
        return {
            "success": False,
            "message": "未导入 Apple Health 数据，请先上传导出文件"
        }

    config = credential.get_config()
    imported_data = config.get("imported_data", {})

    if not imported_data:
        return {
            "success": False,
            "message": "未导入 Apple Health 数据，请先上传导出文件"
        }

    adapter = AppleHealthAdapter(imported_data=imported_data)
    return await adapter.test_connection()


@router.post("/apple/sync", response_model=DeviceSyncResult, summary="同步 Apple Health 数据")
async def sync_apple_data(
    request: SyncRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    同步 Apple Health 数据

    注意：Apple Health 数据来自文件导入，此接口会从已导入的数据中同步到数据库
    """
    from app.services.device_adapters.apple import AppleHealthAdapter

    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id,
        DeviceCredential.device_type == "apple"
    ).first()

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未导入 Apple Health 数据，请先上传导出文件"
        )

    config = credential.get_config()
    imported_data = config.get("imported_data", {})

    if not imported_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未导入 Apple Health 数据，请先上传导出文件"
        )

    adapter = AppleHealthAdapter(imported_data=imported_data)

    synced = 0
    failed = 0
    today = datetime.now().date()

    for i in range(request.days):
        target_date = today - timedelta(days=i)
        try:
            data = await adapter.fetch_daily_data(target_date)
            if data:
                DeviceManager._save_health_data(db, current_user.id, data)
                synced += 1
        except Exception as e:
            logger.warning(f"同步 {target_date} 失败: {e}")
            failed += 1

    credential.update_sync_time()
    credential.mark_valid()
    db.commit()
    _invalidate_twin(current_user.id)

    return DeviceSyncResult(
        success=True,
        device="apple",
        synced_days=synced,
        failed_days=failed,
        message=f"同步完成：成功 {synced} 天，失败 {failed} 天"
    )


# ===== HealthKit (iOS App 主动推送数据) =====

class BPReadingIn(BaseModel):
    """单条血压点事件 — 血压一天多次, 是点事件 (和 ECG 同理), 不塞日聚合避免互相覆盖.

    容错: systolic/diastolic 走 before-validator float→int 取整 (avg() 聚合可能给小数);
    measured_at 是去重锚点 ((user_id, measured_at) 唯一); source 是 HealthKit sourceName,
    仅用于备注, 不参与去重。坏值在 service 层丢弃, 不崩整批。"""
    # systolic/diastolic 也设 Optional + 容错: 坏值 (None / 非数) 不在请求级 422 拖垮
    # 整批, 而是过校验后由 service 层 _save_blood_pressure 丢弃该条 (不崩, 不误写)。
    systolic: Optional[int] = None
    diastolic: Optional[int] = None
    # measured_at 是去重锚点。Optional: 缺失不 422, 由 service 丢弃该条 (无锚点无法去重)。
    measured_at: Optional[datetime] = None
    source: Optional[str] = None

    @field_validator("systolic", "diastolic", mode="before")
    @classmethod
    def _round_bp_to_int(cls, v):
        if isinstance(v, float):
            return round(v)
        return v


class Spo2SampleIn(BaseModel):
    """单条整夜血氧采样点 — RingConn / Apple Watch 等写 HealthKit 的设备的逐分钟序列.

    HealthKit ``HKQuantityTypeIdentifierOxygenSaturation`` 是离散样本: 每条
    ``{value (0-100 百分数), measured_at (ISO)}``。逐分钟 SpO2 是夜间低氧"持续负荷"
    (ODI / below-90% 时长占比) 的唯一数据源 —— 日聚合单点 ``spo2_min`` 无法算这两个
    指标, 而 ``vitals.spo2_min_nocturnal_severe`` 需要它们做佐证才拉 CRITICAL
    (否则降级 INFO, 见 2026-06-17 裁决)。Garmin 血氧已整源剔除, 多设备用户的逐秒
    SpO2 之前无任何入口 → 夜间低氧规则只能靠日聚合单点最低值判断, 本字段补齐缺口。

    - value: HealthKit 原始 0-1 已由 mobile ×100 成百分数; service 层取整 + sanity
      50-100, 坏值丢弃该条 (不崩整批)。Optional → 缺失不 422。
    - measured_at: 决定 sample_time (转 CST HH:MM) 与 epoch_ms; 缺失/坏值 → service 丢弃。
    """
    value: Optional[float] = None
    measured_at: Optional[datetime] = None


class HealthKitDailyRecord(BaseModel):
    """单日 HealthKit 聚合记录 — mobile 端按天预聚合后推上来.

    data_source 标签由 mobile 端按 sourceName 映射决定 (apple-watch / ringconn /
    oura / withings-app / garmin-app / manual / unknown). 字典外的 sourceName
    会落到 unknown,后端不拒绝,只 warning."""
    record_date: str  # ISO date "YYYY-MM-DD"
    data_source: Optional[str] = None  # 优先用此字段;若空,回落 source_name 映射
    source_name: Optional[str] = None  # iOS bundle id, 仅当 data_source 为空时使用

    sleep_score: Optional[int] = None
    total_sleep_minutes: Optional[int] = None
    deep_sleep_minutes: Optional[int] = None
    rem_sleep_minutes: Optional[int] = None
    light_sleep_minutes: Optional[int] = None
    awake_minutes: Optional[int] = None
    sleep_start_time: Optional[str] = None  # "HH:MM:SS" or "HH:MM"
    sleep_end_time: Optional[str] = None

    resting_heart_rate: Optional[int] = None
    avg_heart_rate: Optional[int] = None
    max_heart_rate: Optional[int] = None
    min_heart_rate: Optional[int] = None

    hrv: Optional[float] = None
    hrv_status: Optional[str] = None

    steps: Optional[int] = None
    distance_meters: Optional[float] = None
    floors_climbed: Optional[int] = None
    active_minutes: Optional[int] = None
    calories_total: Optional[int] = None
    calories_active: Optional[int] = None

    stress_level: Optional[int] = None
    body_battery_high: Optional[int] = None
    body_battery_low: Optional[int] = None

    spo2_avg: Optional[float] = None
    spo2_min: Optional[float] = None

    respiration_rate_avg: Optional[float] = None
    respiration_rate_min: Optional[float] = None
    respiration_rate_max: Optional[float] = None

    body_temp_deviation_c: Optional[float] = None

    # ===== ECG (Apple Watch 独有, 房颤筛查信号非诊断) =====
    # 最近一次 ECG 分类, 原样 HealthKit 字符串 (SinusRhythm / AtrialFibrillation /
    # InconclusiveLowHeartRate / InconclusiveHighHeartRate / Unrecognized / ...).
    # 未知/缺失值原样接收, 后端不枚举校验, 下游只对明确 "AtrialFibrillation" 告警.
    ecg_classification: Optional[str] = None
    ecg_recorded_at: Optional[datetime] = None  # 该次 ECG 记录时间 (sample startDate)
    afib_event_count: Optional[int] = None  # 本窗口内 AtrialFibrillation 分类次数, 默认按 0 处理

    # ===== 血压点事件 (一天多次, 不塞日聚合) =====
    # 每条 reading 各自按 (user_id, measured_at) 去重幂等落 blood_pressure_records。
    blood_pressure_readings: Optional[List[BPReadingIn]] = None

    # ===== 整夜逐分钟血氧 (RingConn / Apple Watch 等贴肤光路) =====
    # 逐分钟 SpO2 序列, 落 spo2_samples 表 (与日聚合 spo2_avg/spo2_min 并行)。
    # 这是 ODI / below-90% 持续负荷指标的唯一数据源 —— 夜间严重低氧规则靠它把"真 OSA"
    # 与"单点伪影"区分开。按 (user_id, record_date, data_source) 删后插, 重复上送幂等。
    spo2_samples: Optional[List[Spo2SampleIn]] = None

    # ===== 体脂 (随体重) =====
    # body_fat_percentage 随 weight_kg 一并落 weight_records (weight 列 NOT NULL,
    # body_fat 必须有体重作载体)。只有 body_fat 没 weight → 无法落库, 静默不写 (非错误)。
    weight_kg: Optional[float] = None
    body_fat_percentage: Optional[float] = None

    raw_data: Optional[dict] = None

    # 客户端用 avg()/sum() 聚合,常把小数 float 喂给 int 字段(如 resting_heart_rate
    # =52.5)。Pydantic v2 默认拒绝带小数的 float→int,而且这发生在请求级校验,
    # 一条坏值会让整批 422 → 0 导入(用户实测过)。这里对所有 int 字段做 before
    # 取整,让契约容错:坏值最多被四舍五入,不再拖垮整批。
    @field_validator(
        "sleep_score", "total_sleep_minutes", "deep_sleep_minutes",
        "rem_sleep_minutes", "light_sleep_minutes", "awake_minutes",
        "resting_heart_rate", "avg_heart_rate", "max_heart_rate", "min_heart_rate",
        "steps", "floors_climbed", "active_minutes", "calories_total", "calories_active",
        "stress_level", "body_battery_high", "body_battery_low",
        "afib_event_count",
        mode="before",
    )
    @classmethod
    def _round_floats_to_int(cls, v):
        if isinstance(v, float):
            return round(v)
        return v


class HealthKitImportRequest(BaseModel):
    records: List[HealthKitDailyRecord]


class HealthKitImportError(BaseModel):
    index: int
    # "daily" (日聚合) | "ecg" (ECG 点事件) | "blood_pressure" (血压点事件) |
    # "body_composition" (体重+体脂) | "spo2" (整夜逐分钟血氧序列)
    kind: str = "daily"
    record_date: Optional[str]
    error: str


class HealthKitImportResponse(BaseModel):
    imported_count: int
    ecg_imported_count: int = 0  # 独立落库的 ECG 点事件数 (与日聚合并行, 不依赖其成功)
    blood_pressure_imported_count: int = 0  # 独立落库的血压点事件数 (与日聚合并行)
    spo2_sample_imported_count: int = 0  # 独立落库的整夜逐分钟血氧采样点数 (与日聚合并行)
    source_breakdown: dict  # {"apple-watch": 12, "ringconn": 5, ...}
    errors: List[HealthKitImportError]


# 单批上限 — 前端按月切片 (~30 天/批),给 100 留余量;再大走多批
_HEALTHKIT_BATCH_LIMIT = 100

_HEALTHKIT_PROVIDER = "healthkit"
_HEALTHKIT_IMPORT_TRANSFORM = "healthkit_import_v1"
_HEALTHKIT_SCOPES = {
    "daily": "healthkit.daily.read",
    "ecg": "healthkit.ecg.read",
    "blood_pressure": "healthkit.blood_pressure.read",
    "spo2": "healthkit.spo2.read",
    "body": "healthkit.body.read",
}
_HEALTHKIT_DAILY_FIELDS = frozenset({
    "sleep_score",
    "total_sleep_minutes",
    "deep_sleep_minutes",
    "rem_sleep_minutes",
    "light_sleep_minutes",
    "awake_minutes",
    "sleep_start_time",
    "sleep_end_time",
    "resting_heart_rate",
    "avg_heart_rate",
    "max_heart_rate",
    "min_heart_rate",
    "hrv",
    "hrv_status",
    "steps",
    "distance_meters",
    "floors_climbed",
    "active_minutes",
    "calories_total",
    "calories_active",
    "stress_level",
    "body_battery_high",
    "body_battery_low",
    "respiration_rate_avg",
    "respiration_rate_min",
    "respiration_rate_max",
    "body_temp_deviation_c",
    "raw_data",
})


def _non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, dict, str)):
        return len(value) > 0
    return True


def _healthkit_required_scopes_for_record(record: dict[str, Any]) -> set[str]:
    scopes: set[str] = set()
    if any(_non_empty(record.get(field)) for field in _HEALTHKIT_DAILY_FIELDS):
        scopes.add(_HEALTHKIT_SCOPES["daily"])
    if _non_empty(record.get("ecg_classification")) or _non_empty(record.get("ecg_recorded_at")):
        scopes.add(_HEALTHKIT_SCOPES["ecg"])
    if _non_empty(record.get("afib_event_count")):
        scopes.add(_HEALTHKIT_SCOPES["ecg"])
    if _non_empty(record.get("blood_pressure_readings")):
        scopes.add(_HEALTHKIT_SCOPES["blood_pressure"])
    if _non_empty(record.get("spo2_avg")) or _non_empty(record.get("spo2_min")):
        scopes.add(_HEALTHKIT_SCOPES["spo2"])
    if _non_empty(record.get("spo2_samples")):
        scopes.add(_HEALTHKIT_SCOPES["spo2"])
    if _non_empty(record.get("weight_kg")) or _non_empty(record.get("body_fat_percentage")):
        scopes.add(_HEALTHKIT_SCOPES["body"])
    if not scopes:
        # Empty HealthKit payloads still attempt the daily import path today; require the
        # least-privilege daily scope rather than accepting unscoped writes.
        scopes.add(_HEALTHKIT_SCOPES["daily"])
    return scopes


def _healthkit_required_scopes(records: list[dict[str, Any]]) -> set[str]:
    required: set[str] = set()
    for record in records:
        required.update(_healthkit_required_scopes_for_record(record))
    return required


def _healthkit_missing_scope_detail(required: set[str]) -> str:
    return f"HealthKit consent required for scopes: {', '.join(sorted(required))}"


def _expires_in_future(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc)


def _require_active_healthkit_import_consent(
    db: Session,
    *,
    user_id: int,
    required_scopes: set[str],
):
    from app.models.data_connection import ConsentGrant, DataConnection
    from app.services.data_connections import ACTIVE_GRANT_STATUS

    connections = (
        db.query(DataConnection)
        .filter(
            DataConnection.user_id == user_id,
            DataConnection.provider == _HEALTHKIT_PROVIDER,
            DataConnection.connection_status == "active",
            DataConnection.token_status != "revoked",
        )
        .order_by(DataConnection.id.desc())
        .all()
    )
    for connection in connections:
        connection_scopes = set(connection.scopes or [])
        if not required_scopes.issubset(connection_scopes):
            continue
        grants = (
            db.query(ConsentGrant)
            .filter(
                ConsentGrant.user_id == user_id,
                ConsentGrant.connection_id == connection.id,
                ConsentGrant.status == ACTIVE_GRANT_STATUS,
                ConsentGrant.grantee_type == "self",
            )
            .order_by(ConsentGrant.granted_at.desc(), ConsentGrant.id.desc())
            .all()
        )
        for grant in grants:
            if not _expires_in_future(grant.expires_at):
                continue
            if required_scopes.issubset(set(grant.scopes or [])):
                return connection

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=_healthkit_missing_scope_detail(required_scopes),
    )


def _healthkit_payload_hash(record: dict[str, Any]) -> str:
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _healthkit_present_fields(record: dict[str, Any]) -> list[str]:
    return sorted(key for key, value in record.items() if _non_empty(value))


def _record_healthkit_provenance(
    db: Session,
    *,
    user_id: int,
    connection_id: int,
    records: list[dict[str, Any]],
) -> None:
    from app.services.data_connections import create_provenance_record
    from app.services.device_adapters.healthkit import HealthKitAdapter

    for index, record in enumerate(records):
        data_source = HealthKitAdapter._resolve_data_source(record)
        record_scopes = _healthkit_required_scopes_for_record(record)
        record_date = str(record.get("record_date")) if record.get("record_date") else "unknown-date"
        object_id = f"{record_date}:{data_source}:{index}:{_healthkit_payload_hash(record)[:12]}"
        create_provenance_record(
            db,
            user_id=user_id,
            connection_id=connection_id,
            source_kind=_HEALTHKIT_PROVIDER,
            source_id=data_source,
            object_type="HealthKitDailyRecord",
            object_id=object_id,
            transformed_by=_HEALTHKIT_IMPORT_TRANSFORM,
            confidence="device_reported",
            privacy_classification="L3",
            raw_hash=_healthkit_payload_hash(record),
            metadata={
                "required_scopes": sorted(record_scopes),
                "record_date": str(record.get("record_date")) if record.get("record_date") else None,
                "data_source": data_source,
                "source_name": record.get("source_name"),
                "fields_present": _healthkit_present_fields(record),
                "import_index": index,
            },
        )


@router.post(
    "/healthkit/import",
    response_model=HealthKitImportResponse,
    summary="HealthKit 数据导入",
    description=(
        "iOS App 端从 HealthKit 读取并按天聚合后,通过此端点 POST 推送. "
        "支持 Apple Watch / RingConn / Oura / Withings App / 其他写 HealthKit 的设备. "
        "(user_id, record_date, data_source) 复合唯一,重复 POST 幂等."
    ),
)
async def healthkit_import(
    request: HealthKitImportRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if len(request.records) > _HEALTHKIT_BATCH_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"单批最多 {_HEALTHKIT_BATCH_LIMIT} 条记录,请按月分批 (当前 {len(request.records)} 条)",
        )

    from app.services.device_adapters.healthkit import HealthKitAdapter
    from app.services.data_connections import record_sync_result

    records = [r.model_dump() for r in request.records]
    required_scopes = _healthkit_required_scopes(records)
    connection = _require_active_healthkit_import_consent(
        db,
        user_id=current_user.id,
        required_scopes=required_scopes,
    )
    _record_healthkit_provenance(
        db,
        user_id=current_user.id,
        connection_id=connection.id,
        records=records,
    )
    result = HealthKitAdapter.batch_save(db, current_user.id, records)
    # 诚实性: 按实际落库量派生 success。batch_save 逐条独立 try/except、从不抛异常,
    # 整批失败时 imported_count/ecg/bp/spo2 全 0 且 errors 非空。无条件 success=True
    # 会把连接置 active、抹掉真实 sync_error → 设备源 UI 谎报"刚同步成功"、agent 新鲜度
    # 误判 fresh, 实为 noop。空批(无记录无错误)保持 success=True。
    imported_any = (
        result["imported_count"]
        + result["ecg_imported_count"]
        + result["blood_pressure_imported_count"]
        + result["spo2_sample_imported_count"]
    ) > 0
    if not imported_any and result["errors"]:
        # 脱敏: connection.sync_error 是明文 Text 列, 且经 GET /devices 系列反复回吐 + 进备份。
        # errors[i]['error'] = f"{type(e).__name__}: {e}", 其中 {e} 的 SQLAlchemy repr 可能内嵌
        # 绑定参数=原始健康值(BP/体重/SpO2/ECG 分类)。只持久化 kind + 异常类名(冒号前 token,
        # 恒无值)——诚实性(连接置 degraded + 失败类别)完全保留, 不回灌原始测量值。§5 硬线。
        _first = result["errors"][0]
        _reason = (_first.get("error") or "").split(":", 1)[0].strip() or "unknown"
        record_sync_result(
            db,
            user_id=current_user.id,
            connection_id=connection.id,
            success=False,
            error_message=(
                f"{len(result['errors'])}条全部导入失败: "
                f"{_first.get('kind', '?')}/{_reason}"
            ),
        )
    else:
        record_sync_result(
            db,
            user_id=current_user.id,
            connection_id=connection.id,
            success=True,
        )
    _invalidate_twin(current_user.id)

    logger.info(
        f"[healthkit_import] user={current_user.id} batch={len(records)} "
        f"imported={result['imported_count']} ecg_imported={result['ecg_imported_count']} "
        f"bp_imported={result['blood_pressure_imported_count']} "
        f"spo2_samples={result['spo2_sample_imported_count']} "
        f"sources={result['source_breakdown']} errors={len(result['errors'])}"
    )

    return HealthKitImportResponse(
        imported_count=result["imported_count"],
        ecg_imported_count=result["ecg_imported_count"],
        blood_pressure_imported_count=result["blood_pressure_imported_count"],
        spo2_sample_imported_count=result["spo2_sample_imported_count"],
        source_breakdown=result["source_breakdown"],
        errors=[HealthKitImportError(**e) for e in result["errors"]],
    )
