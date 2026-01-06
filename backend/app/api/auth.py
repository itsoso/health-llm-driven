"""用户认证API"""
from datetime import datetime, timedelta, date
from typing import Optional, AsyncGenerator
import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User, GarminCredential
from app.schemas.auth import (
    UserRegister, UserLogin, Token, UserResponse, UserUpdate,
    PasswordChange, GarminCredentialCreate, GarminCredentialResponse,
    GarminSyncRequest, GarminSyncResponse
)
from app.services.auth import auth_service, garmin_credential_service, AuthService
import logging
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()

# OAuth2 密码流配置
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """获取当前登录用户"""
    if not token:
        return None
    
    payload = auth_service.decode_token(token)
    if not payload:
        return None
    
    user_id = payload.get("sub")
    if not user_id:
        return None
    
    user = auth_service.get_user_by_id(db, int(user_id))
    return user


async def get_current_user_required(
    current_user: Optional[User] = Depends(get_current_user)
) -> User:
    """获取当前登录用户（必须登录）"""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或登录已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )
    return current_user


def user_to_response(user: User, db: Session) -> UserResponse:
    """将User模型转换为响应"""
    has_garmin = db.query(GarminCredential).filter(GarminCredential.user_id == user.id).first() is not None
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        name=user.name,
        birth_date=user.birth_date,
        gender=user.gender,
        is_active=user.is_active if user.is_active is not None else True,
        is_admin=getattr(user, 'is_admin', False) or False,
        created_at=user.created_at,
        has_garmin_credentials=has_garmin
    )


@router.post("/register", response_model=Token, summary="用户注册")
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """
    用户注册
    
    - **username**: 用户名（3-50字符，唯一）
    - **email**: 邮箱（唯一）
    - **password**: 密码（至少6字符）
    - **name**: 姓名
    """
    # 检查用户名是否已存在
    if auth_service.get_user_by_username(db, user_data.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已被注册"
        )
    
    # 检查邮箱是否已存在
    if auth_service.get_user_by_email(db, user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已被注册"
        )
    
    # 创建用户
    user = auth_service.create_user(
        db=db,
        username=user_data.username,
        email=user_data.email,
        password=user_data.password,
        name=user_data.name
    )
    
    # 生成令牌
    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "username": user.username}
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=user_to_response(user, db)
    )


@router.post("/login", response_model=Token, summary="用户登录")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    用户登录（OAuth2密码流）
    
    - **username**: 用户名或邮箱
    - **password**: 密码
    """
    user = auth_service.authenticate_user(db, form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )
    
    # 生成令牌
    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "username": user.username}
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=user_to_response(user, db)
    )


@router.post("/login/json", response_model=Token, summary="用户登录（JSON格式）")
async def login_json(login_data: UserLogin, db: Session = Depends(get_db)):
    """
    用户登录（JSON格式）
    
    - **username**: 用户名或邮箱
    - **password**: 密码
    """
    user = auth_service.authenticate_user(db, login_data.username, login_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )
    
    # 生成令牌
    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "username": user.username}
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=user_to_response(user, db)
    )


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_me(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前登录用户的信息"""
    return user_to_response(current_user, db)


@router.put("/me", response_model=UserResponse, summary="更新用户信息")
async def update_me(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新当前用户信息"""
    if user_update.name is not None:
        current_user.name = user_update.name
    if user_update.birth_date is not None:
        current_user.birth_date = user_update.birth_date
    if user_update.gender is not None:
        current_user.gender = user_update.gender
    
    db.commit()
    db.refresh(current_user)
    return user_to_response(current_user, db)


@router.post("/change-password", summary="修改密码")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """修改当前用户密码"""
    # 验证旧密码
    if not auth_service.verify_password(password_data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误"
        )
    
    # 更新密码
    current_user.hashed_password = auth_service.get_password_hash(password_data.new_password)
    db.commit()
    
    return {"message": "密码修改成功"}


# ========== Garmin凭证管理 ==========

@router.post("/garmin/credentials", response_model=GarminCredentialResponse, summary="保存Garmin凭证")
async def save_garmin_credentials(
    credentials: GarminCredentialCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    保存Garmin登录凭证
    
    凭证会被加密存储，用于后续自动同步Garmin数据
    """
    credential = garmin_credential_service.save_credentials(
        db=db,
        user_id=current_user.id,
        garmin_email=credentials.garmin_email,
        garmin_password=credentials.garmin_password
    )
    return credential


@router.get("/garmin/credentials", response_model=GarminCredentialResponse, summary="获取Garmin凭证信息")
async def get_garmin_credentials(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的Garmin凭证信息（不包含密码）"""
    credential = garmin_credential_service.get_credentials(db, current_user.id)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未配置Garmin凭证"
        )
    return credential


@router.delete("/garmin/credentials", summary="删除Garmin凭证")
async def delete_garmin_credentials(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除当前用户的Garmin凭证"""
    if garmin_credential_service.delete_credentials(db, current_user.id):
        return {"message": "Garmin凭证已删除"}
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="未配置Garmin凭证"
    )


@router.post("/garmin/toggle-sync", summary="切换Garmin同步状态")
async def toggle_garmin_sync(
    enabled: bool,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    启用或禁用Garmin自动同步
    
    - **enabled**: True 启用同步，False 停止同步
    """
    credential = garmin_credential_service.get_credentials(db, current_user.id)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未配置Garmin凭证"
        )
    
    if garmin_credential_service.toggle_sync_enabled(db, current_user.id, enabled):
        return {
            "message": f"Garmin同步已{'启用' if enabled else '停止'}",
            "sync_enabled": enabled
        }
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="更新同步状态失败"
    )


@router.post("/garmin/sync", response_model=GarminSyncResponse, summary="同步Garmin数据")
async def sync_garmin_data(
    sync_request: GarminSyncRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    手动触发Garmin数据同步
    
    - **days**: 同步最近N天的数据（默认7天，最多730天）
    """
    # 获取解密后的凭证
    credentials = garmin_credential_service.get_decrypted_credentials(db, current_user.id)
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未配置Garmin凭证，请先在设置中配置"
        )
    
    # 执行同步
    try:
        from app.services.data_collection.garmin_connect import GarminConnectService
        from datetime import date, timedelta
        
        # 创建Garmin服务实例（传入凭证，会自动登录）
        garmin_service = GarminConnectService(
            email=credentials["email"],
            password=credentials["password"]
        )
        
        # 同步数据
        synced_days = 0
        failed_days = 0
        today = date.today()
        
        for i in range(sync_request.days):
            target_date = today - timedelta(days=i)
            try:
                garmin_service.sync_daily_data(db, current_user.id, target_date)
                synced_days += 1
            except Exception as e:
                logger.warning(f"同步 {target_date} 失败: {e}")
                failed_days += 1
        
        # 更新同步状态
        garmin_credential_service.update_sync_status(db, current_user.id)
        
        return GarminSyncResponse(
            success=True,
            message=f"同步完成：成功 {synced_days} 天，失败 {failed_days} 天",
            synced_days=synced_days,
            failed_days=failed_days
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Garmin同步失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"同步失败: {str(e)}"
        )


@router.get("/garmin/sync-stream", summary="流式同步Garmin数据（带进度）")
async def sync_garmin_data_stream(
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    使用 Server-Sent Events 流式同步Garmin数据，实时返回进度
    """
    # 获取解密后的凭证
    credentials = garmin_credential_service.get_decrypted_credentials(db, current_user.id)
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未配置Garmin凭证，请先在设置中配置"
        )
    
    async def generate_progress() -> AsyncGenerator[str, None]:
        from app.services.data_collection.garmin_connect import GarminConnectService
        
        synced_days = 0
        failed_days = 0
        today = date.today()
        
        # 发送开始消息
        yield f"data: {json.dumps({'type': 'start', 'total': days, 'message': '开始同步...'})}\n\n"
        
        try:
            # 创建Garmin服务实例
            garmin_service = GarminConnectService(
                email=credentials["email"],
                password=credentials["password"]
            )
            
            yield f"data: {json.dumps({'type': 'progress', 'current': 0, 'total': days, 'message': 'Garmin连接成功'})}\n\n"
            
            for i in range(days):
                target_date = today - timedelta(days=i)
                date_str = target_date.strftime("%Y-%m-%d")
                
                try:
                    garmin_service.sync_daily_data(db, current_user.id, target_date)
                    synced_days += 1
                    status_msg = "success"
                except Exception as e:
                    logger.warning(f"同步 {target_date} 失败: {e}")
                    failed_days += 1
                    status_msg = "failed"
                
                # 发送进度更新
                progress_data = {
                    'type': 'progress',
                    'current': i + 1,
                    'total': days,
                    'date': date_str,
                    'status': status_msg,
                    'synced': synced_days,
                    'failed': failed_days,
                    'message': f'正在同步 {date_str}...'
                }
                yield f"data: {json.dumps(progress_data)}\n\n"
                
                # 小延迟，让前端有时间处理
                await asyncio.sleep(0.1)
            
            # 更新同步状态
            garmin_credential_service.update_sync_status(db, current_user.id)
            
            # 发送完成消息
            complete_data = {
                'type': 'complete',
                'synced': synced_days,
                'failed': failed_days,
                'message': f'同步完成：成功 {synced_days} 天，失败 {failed_days} 天'
            }
            yield f"data: {json.dumps(complete_data)}\n\n"
            
        except Exception as e:
            logger.error(f"Garmin同步失败: {e}", exc_info=True)
            error_data = {
                'type': 'error',
                'message': f'同步失败: {str(e)}'
            }
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        }
    )


@router.post("/garmin/test-connection", summary="测试Garmin连接")
async def test_garmin_connection(
    credentials: GarminCredentialCreate,
    current_user: User = Depends(get_current_user_required)
):
    """
    测试Garmin凭证是否有效（不保存）
    
    返回明确的提示信息：
    - 成功：✅ 密码正确，连接成功
    - 失败：❌ 密码错误或账号无效
    """
    try:
        from app.services.data_collection.garmin_connect import GarminConnectService, GarminAuthenticationError
        
        # 创建服务实例时会尝试登录
        garmin_service = GarminConnectService(
            email=credentials.garmin_email,
            password=credentials.garmin_password
        )
        # 尝试获取今天的数据来验证凭证
        from datetime import date
        summary = garmin_service.get_user_summary(date.today())
        if summary is not None:
            return {
                "success": True, 
                "message": "✅ 密码正确！Garmin账号连接成功，可以保存凭证了。"
            }
        else:
            return {
                "success": True, 
                "message": "✅ 密码正确！连接成功（今日暂无同步数据）"
            }
    except GarminAuthenticationError as e:
        logger.warning(f"测试Garmin连接失败 - 认证错误: {e}")
        error_str = str(e)
        # 检查是否需要设置密码
        if '设置密码' in error_str or 'set password' in error_str.lower():
            return {
                "success": False, 
                "message": "⚠️ Garmin账号需要设置密码！请先访问 connect.garmin.com 登录并按提示完成密码设置，然后再尝试连接。"
            }
        return {
            "success": False, 
            "message": "❌ 密码错误或账号无效！请检查您的Garmin Connect邮箱和密码是否正确。"
        }
    except Exception as e:
        logger.error(f"测试Garmin连接失败: {e}")
        error_msg = str(e).lower()
        # 检查是否需要设置密码
        if 'set password' in error_msg or 'unexpected title' in error_msg:
            return {
                "success": False, 
                "message": "⚠️ Garmin账号需要设置密码！请先访问 connect.garmin.com 登录并按提示完成密码设置。"
            }
        if any(kw in error_msg for kw in ['401', 'unauthorized', 'credential', 'password', 'login', 'auth', 'oauth']):
            return {
                "success": False, 
                "message": "❌ 密码错误或账号无效！请检查您的Garmin Connect邮箱和密码是否正确。"
            }
        return {
            "success": False, 
            "message": f"❌ 连接失败: {str(e)}"
        }

