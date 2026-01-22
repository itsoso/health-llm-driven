"""
Garmin 数据同步任务
"""
import logging
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.user import User
from app.models.device_credential import DeviceCredential
from app.services.data_collection.garmin_connect import GarminConnectService

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def sync_user_garmin_data(self, user_id: int):
    """
    同步单个用户的 Garmin 数据
    """
    logger.info(f"开始同步用户 {user_id} 的 Garmin 数据")
    
    try:
        with SessionLocal() as db:
            credential = db.query(DeviceCredential).filter(
                DeviceCredential.user_id == user_id,
                DeviceCredential.device_type == "garmin"
            ).first()
            
            if not credential:
                logger.warning(f"用户 {user_id} 没有 Garmin 凭据")
                return {"status": "skipped", "reason": "no_credentials"}
            
            # 获取凭证
            creds = credential.get_credentials()
            
            # 创建服务并同步
            service = GarminConnectService(
                email=creds.get("email"),
                password=creds.get("password"),
                user_id=user_id
            )
            
            result = service.sync_all_data(db, days=1)
            
            logger.info(f"用户 {user_id} Garmin 同步完成: {result}")
            return {"status": "success", "result": result}
            
    except Exception as e:
        logger.error(f"用户 {user_id} Garmin 同步失败: {e}")
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


@celery_app.task
def sync_all_users_garmin():
    """
    同步所有用户的 Garmin 数据（每小时执行）
    """
    logger.info("开始批量同步所有用户 Garmin 数据")
    
    with SessionLocal() as db:
        credentials = db.query(DeviceCredential).filter(
            DeviceCredential.device_type == "garmin",
            DeviceCredential.is_active == True
        ).all()
        
        user_ids = [c.user_id for c in credentials]
    
    logger.info(f"发现 {len(user_ids)} 个活跃的 Garmin 账户")
    
    # 为每个用户创建异步任务
    for user_id in user_ids:
        sync_user_garmin_data.delay(user_id)
    
    return {"status": "dispatched", "count": len(user_ids)}
