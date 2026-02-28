"""
Withings 设备集成 API

提供 OAuth 授权、Webhook 接收、数据同步功能。
Webhook 数据自动注入到健康事件流系统。
"""
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.device_credential import DeviceCredential
from app.services.device_adapters.withings import (
    WithingsHealthAdapter,
    APPLI_WEIGHT, APPLI_PRESSURE, APPLI_SLEEP,
)
from app.services.health_event_service import HealthEventService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices/withings", tags=["withings"])

WEBHOOK_BASE = "https://health-api.executor.life/api/v1/devices/withings/webhook"


# ========== OAuth 授权流程 ==========

@router.get("/oauth/authorize", summary="获取 Withings 授权 URL")
async def get_withings_oauth_url(
    redirect_uri: str = Query(
        default="https://health-api.executor.life/api/v1/devices/withings/oauth/callback",
        description="授权后的回调地址",
    ),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取 Withings OAuth 授权 URL，用户访问后跳转到 Withings 登录页。"""
    state = f"{current_user.id}:{secrets.token_urlsafe(16)}"

    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id,
        DeviceCredential.device_type == "withings",
    ).first()

    if not credential:
        credential = DeviceCredential(
            user_id=current_user.id,
            device_type="withings",
            auth_type="oauth2",
            is_valid=False,
        )
        db.add(credential)

    credential.set_config({"oauth_state": state, "redirect_uri": redirect_uri})
    db.commit()

    adapter = WithingsHealthAdapter()
    auth_url = adapter.get_oauth_url(redirect_uri, state)

    return {
        "auth_url": auth_url,
        "state": state,
        "message": "请访问 auth_url 完成 Withings 授权",
    }


@router.get("/oauth/callback", summary="Withings OAuth 回调")
async def withings_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Withings OAuth 回调 - 用授权码换取 token。
    授权成功后自动订阅 Webhook。
    """
    # 解析 state 中的 user_id
    try:
        user_id_str, _ = state.split(":", 1)
        user_id = int(user_id_str)
    except Exception:
        return HTMLResponse(content=_error_html("无效的授权参数"), status_code=400)

    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == user_id,
        DeviceCredential.device_type == "withings",
    ).first()

    if not credential:
        return HTMLResponse(content=_error_html("未找到授权请求"), status_code=404)

    config = credential.get_config()
    if config.get("oauth_state") != state:
        return HTMLResponse(content=_error_html("授权验证失败"), status_code=400)

    # 换取 token
    try:
        adapter = WithingsHealthAdapter()
        token_result = await adapter.exchange_code_for_token(
            code, config.get("redirect_uri", "")
        )

        # 保存 token（access_token 有效期 3 小时）
        expires_at = datetime.now() + timedelta(seconds=token_result.get("expires_in", 10800))
        credential.set_oauth_tokens(
            access_token=token_result["access_token"],
            refresh_token=token_result.get("refresh_token"),
            expires_at=expires_at,
            scope=token_result.get("scope", ""),
        )
        credential.mark_valid()
        credential.update_sync_time()

        # 保存 userid（Withings 用户 ID，Webhook 中会用到）
        config["withings_userid"] = token_result.get("userid")
        config.pop("oauth_state", None)
        credential.set_config(config)
        db.commit()

        # 自动订阅 Webhook
        try:
            await adapter.subscribe_all_webhooks(WEBHOOK_BASE)
            logger.info(f"Withings webhooks subscribed for user {user_id}")
        except Exception as e:
            logger.warning(f"Withings webhook subscribe failed: {e}")

        return HTMLResponse(content=_success_html())

    except Exception as e:
        logger.error(f"Withings OAuth callback failed: {e}")
        credential.mark_invalid(str(e))
        db.commit()
        return HTMLResponse(content=_error_html(f"授权失败: {e}"), status_code=400)


# ========== Webhook 接收 ==========

@router.post("/webhook", summary="Withings Webhook 接收")
@router.get("/webhook", summary="Withings Webhook 验证")
async def withings_webhook(request: Request, db: Session = Depends(get_db)):
    """
    接收 Withings Webhook 通知。

    GET: Withings 验证回调 URL 是否可达（需返回其发送的数据）
    POST: 接收实际的数据通知
    """
    if request.method == "GET":
        # Withings 验证 Webhook URL - 需要原样返回请求体
        return HTMLResponse(content="OK", status_code=200)

    # POST: 接收通知
    try:
        body = await request.form()
        userid = body.get("userid")
        appli = int(body.get("appli", 0))
        startdate = int(body.get("startdate", 0))
        enddate = int(body.get("enddate", 0))

        logger.info(f"Withings webhook: userid={userid}, appli={appli}, "
                     f"startdate={startdate}, enddate={enddate}")

        if not userid or not startdate:
            return {"status": "ignored", "reason": "missing params"}

        # 找到对应的用户凭证
        credentials = db.query(DeviceCredential).filter(
            DeviceCredential.device_type == "withings",
            DeviceCredential.is_valid == True,
        ).all()

        target_credential = None
        for cred in credentials:
            config = cred.get_config()
            if str(config.get("withings_userid")) == str(userid):
                target_credential = cred
                break

        if not target_credential:
            logger.warning(f"Withings webhook: no credential found for userid={userid}")
            return {"status": "ignored", "reason": "user not found"}

        # 创建适配器拉取实际数据
        adapter = WithingsHealthAdapter(
            access_token=target_credential.get_access_token(),
            refresh_token=target_credential.get_refresh_token(),
        )

        # 根据 appli 类型处理
        event_service = HealthEventService(db)

        if appli == APPLI_WEIGHT:
            await _handle_weight_webhook(
                adapter, event_service, target_credential.user_id,
                startdate, enddate,
            )
        elif appli == APPLI_PRESSURE:
            await _handle_pressure_webhook(
                adapter, event_service, target_credential.user_id,
                startdate, enddate,
            )
        elif appli == APPLI_SLEEP:
            await _handle_sleep_webhook(
                adapter, event_service, target_credential.user_id,
                startdate, enddate,
            )
        else:
            logger.info(f"Withings webhook: unhandled appli={appli}")

        # 刷新 token 后保存回去（_api_request 可能刷新了 token）
        if adapter.access_token != target_credential.get_access_token():
            target_credential.set_oauth_tokens(
                access_token=adapter.access_token,
                refresh_token=adapter._refresh_token,
                expires_at=datetime.now() + timedelta(hours=3),
            )
            db.commit()

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Withings webhook error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ========== 手动操作 ==========

@router.post("/sync", summary="手动同步 Withings 数据")
async def sync_withings_data(
    days: int = Query(default=7, le=30),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """手动拉取最近 N 天的 Withings 数据"""
    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id,
        DeviceCredential.device_type == "withings",
        DeviceCredential.is_valid == True,
    ).first()

    if not credential:
        raise HTTPException(status_code=404, detail="未绑定 Withings 设备")

    adapter = WithingsHealthAdapter(
        access_token=credential.get_access_token(),
        refresh_token=credential.get_refresh_token(),
    )

    event_service = HealthEventService(db)
    import time
    now = int(time.time())
    startdate = now - days * 86400

    try:
        measures = await adapter.get_measures_by_timestamp(startdate, now)
        parsed = WithingsHealthAdapter.parse_webhook_measures(measures)

        events_created = 0
        for record in parsed:
            if "weight" in record:
                event_service.ingest_event(
                    user_id=current_user.id,
                    event_type="weight",
                    source="withings",
                    raw_data=record,
                )
                events_created += 1
            if "systolic" in record:
                event_service.ingest_event(
                    user_id=current_user.id,
                    event_type="blood_pressure",
                    source="withings",
                    raw_data=record,
                )
                events_created += 1

        # 保存可能刷新的 token
        if adapter.access_token != credential.get_access_token():
            credential.set_oauth_tokens(
                access_token=adapter.access_token,
                refresh_token=adapter._refresh_token,
                expires_at=datetime.now() + timedelta(hours=3),
            )

        credential.update_sync_time()
        db.commit()

        return {
            "success": True,
            "events_created": events_created,
            "records_found": len(parsed),
            "message": f"同步完成，创建 {events_created} 个事件",
        }
    except Exception as e:
        logger.error(f"Withings sync error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"同步失败: {e}")


@router.post("/webhooks/subscribe", summary="手动订阅 Webhook")
async def subscribe_webhooks(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """手动订阅 Withings Webhook（通常授权时自动订阅）"""
    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id,
        DeviceCredential.device_type == "withings",
        DeviceCredential.is_valid == True,
    ).first()

    if not credential:
        raise HTTPException(status_code=404, detail="未绑定 Withings 设备")

    adapter = WithingsHealthAdapter(
        access_token=credential.get_access_token(),
        refresh_token=credential.get_refresh_token(),
    )

    results = await adapter.subscribe_all_webhooks(WEBHOOK_BASE)

    # 保存可能刷新的 token
    if adapter.access_token != credential.get_access_token():
        credential.set_oauth_tokens(
            access_token=adapter.access_token,
            refresh_token=adapter._refresh_token,
            expires_at=datetime.now() + timedelta(hours=3),
        )
        db.commit()

    return {"results": results}


@router.get("/webhooks/list", summary="查看已订阅的 Webhook")
async def list_webhooks(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """查看当前 Withings Webhook 订阅状态"""
    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id,
        DeviceCredential.device_type == "withings",
        DeviceCredential.is_valid == True,
    ).first()

    if not credential:
        raise HTTPException(status_code=404, detail="未绑定 Withings 设备")

    adapter = WithingsHealthAdapter(
        access_token=credential.get_access_token(),
        refresh_token=credential.get_refresh_token(),
    )

    result = await adapter.list_webhooks()
    return result


@router.get("/status", summary="查看 Withings 绑定状态")
async def get_withings_status(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """查看 Withings 设备绑定和同步状态"""
    credential = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id,
        DeviceCredential.device_type == "withings",
    ).first()

    if not credential:
        return {"bound": False, "message": "未绑定 Withings"}

    return {
        "bound": True,
        "is_valid": credential.is_valid,
        "last_sync_at": credential.last_sync_at.isoformat() if credential.last_sync_at else None,
        "last_error": credential.last_error,
        "withings_userid": credential.get_config().get("withings_userid"),
    }


# ========== Webhook 处理函数 ==========

async def _handle_weight_webhook(
    adapter: WithingsHealthAdapter,
    event_service: HealthEventService,
    user_id: int,
    startdate: int,
    enddate: int,
):
    """处理体重/体脂 Webhook"""
    measures = await adapter.get_measures_by_timestamp(startdate, enddate)
    parsed = WithingsHealthAdapter.parse_webhook_measures(measures)

    for record in parsed:
        if "weight" in record:
            event_service.ingest_event(
                user_id=user_id,
                event_type="weight",
                source="withings",
                raw_data=record,
            )
            logger.info(f"Withings weight event: {record.get('weight')}kg for user {user_id}")


async def _handle_pressure_webhook(
    adapter: WithingsHealthAdapter,
    event_service: HealthEventService,
    user_id: int,
    startdate: int,
    enddate: int,
):
    """处理血压 Webhook"""
    measures = await adapter.get_measures_by_timestamp(startdate, enddate)
    parsed = WithingsHealthAdapter.parse_webhook_measures(measures)

    for record in parsed:
        if "systolic" in record:
            event_service.ingest_event(
                user_id=user_id,
                event_type="blood_pressure",
                source="withings",
                raw_data=record,
            )
            logger.info(f"Withings BP event: {record.get('systolic')}/{record.get('diastolic')} "
                         f"for user {user_id}")


async def _handle_sleep_webhook(
    adapter: WithingsHealthAdapter,
    event_service: HealthEventService,
    user_id: int,
    startdate: int,
    enddate: int,
):
    """处理睡眠 Webhook"""
    from datetime import date as date_type
    target_date = date_type.fromtimestamp(startdate)
    sleep_data = await adapter._get_sleep(target_date)

    if sleep_data.get("series"):
        event_service.ingest_event(
            user_id=user_id,
            event_type="sleep",
            source="withings",
            raw_data=sleep_data,
        )
        logger.info(f"Withings sleep event for user {user_id}")


# ========== HTML 模板 ==========

def _success_html() -> str:
    return """
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body style="font-family: -apple-system, sans-serif; padding: 40px; text-align: center; background: #f0fdf4;">
        <div style="max-width: 400px; margin: 60px auto; background: white; border-radius: 16px; padding: 40px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
            <div style="font-size: 48px; margin-bottom: 16px;">✅</div>
            <h2 style="color: #16a34a; margin-bottom: 8px;">Withings 授权成功</h2>
            <p style="color: #6b7280;">设备数据将自动同步到你的健康系统</p>
            <p style="color: #9ca3af; font-size: 14px; margin-top: 24px;">你可以关闭此页面</p>
        </div>
    </body>
    </html>
    """


def _error_html(message: str) -> str:
    return f"""
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body style="font-family: -apple-system, sans-serif; padding: 40px; text-align: center; background: #fef2f2;">
        <div style="max-width: 400px; margin: 60px auto; background: white; border-radius: 16px; padding: 40px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
            <div style="font-size: 48px; margin-bottom: 16px;">❌</div>
            <h2 style="color: #ef4444; margin-bottom: 8px;">授权失败</h2>
            <p style="color: #6b7280;">{message}</p>
            <p style="color: #9ca3af; font-size: 14px; margin-top: 24px;">请返回应用重试</p>
        </div>
    </body>
    </html>
    """
