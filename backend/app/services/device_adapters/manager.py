"""
设备管理器

统一管理所有设备适配器，提供：
- 设备注册与发现
- 适配器创建
- 数据同步
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Type, Optional, Any
from sqlalchemy.orm import Session

from .base import DeviceAdapter, DeviceType, NormalizedHealthData
from app.models.device_credential import DeviceCredential

logger = logging.getLogger(__name__)


class DeviceManager:
    """
    设备管理器
    
    使用单例模式管理所有设备适配器
    """
    
    # 注册的适配器类
    _adapters: Dict[str, Type[DeviceAdapter]] = {}
    
    @classmethod
    def register_adapter(cls, device_type: str, adapter_class: Type[DeviceAdapter]):
        """
        注册设备适配器（插件机制）
        
        Args:
            device_type: 设备类型标识
            adapter_class: 适配器类
        """
        cls._adapters[device_type] = adapter_class
        logger.info(f"注册设备适配器: {device_type} -> {adapter_class.__name__}")
    
    @classmethod
    def get_supported_devices(cls) -> List[Dict[str, str]]:
        """
        获取支持的设备列表
        
        Returns:
            [{"type": "garmin", "name": "Garmin", "auth_type": "password"}, ...]
        """
        devices = []
        for device_type, adapter_class in cls._adapters.items():
            try:
                # 创建临时实例获取元数据
                adapter = adapter_class()
                devices.append({
                    "type": device_type,
                    "name": adapter.display_name,
                    "auth_type": adapter.auth_type.value,
                })
            except Exception as e:
                logger.warning(f"获取设备信息失败 ({device_type}): {e}")
                devices.append({
                    "type": device_type,
                    "name": device_type.title(),
                    "auth_type": "unknown",
                })
        return devices
    
    @classmethod
    def is_supported(cls, device_type: str) -> bool:
        """检查设备类型是否支持"""
        return device_type in cls._adapters
    
    @classmethod
    def create_adapter(cls, device_type: str, **kwargs) -> DeviceAdapter:
        """
        创建设备适配器实例
        
        Args:
            device_type: 设备类型
            **kwargs: 传递给适配器的参数
            
        Returns:
            适配器实例
            
        Raises:
            ValueError: 不支持的设备类型
        """
        if device_type not in cls._adapters:
            raise ValueError(f"不支持的设备类型: {device_type}，支持的类型: {list(cls._adapters.keys())}")
        
        adapter_class = cls._adapters[device_type]
        return adapter_class(**kwargs)
    
    @classmethod
    def create_adapter_from_credential(
        cls, 
        credential: DeviceCredential
    ) -> DeviceAdapter:
        """
        从凭证记录创建适配器
        
        Args:
            credential: 设备凭证记录
            
        Returns:
            配置好的适配器实例
        """
        device_type = credential.device_type
        
        if device_type not in cls._adapters:
            raise ValueError(f"不支持的设备类型: {device_type}")
        
        adapter_class = cls._adapters[device_type]
        config = credential.get_config()
        
        # 根据认证类型准备参数
        if credential.auth_type == "password":
            # 账号密码认证 (Garmin)
            creds = credential.get_credentials()
            return adapter_class(
                email=creds.get("email"),
                password=creds.get("password"),
                is_cn=config.get("is_cn", False),
            )
        elif credential.auth_type == "oauth2":
            # OAuth 认证 (华为、Fitbit)
            return adapter_class(
                access_token=credential.get_access_token(),
                refresh_token=credential.get_refresh_token(),
                is_cn=config.get("is_cn", True),
            )
        else:
            return adapter_class(**config)
    
    @classmethod
    async def sync_device_data(
        cls,
        db: Session,
        user_id: int,
        device_type: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        同步指定设备的数据
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            device_type: 设备类型
            days: 同步天数
            
        Returns:
            {"success": True, "synced_days": 7, "message": "..."}
        """
        # 获取用户的设备凭证
        credential = db.query(DeviceCredential).filter(
            DeviceCredential.user_id == user_id,
            DeviceCredential.device_type == device_type,
            DeviceCredential.is_valid == True
        ).first()
        
        if not credential:
            return {
                "success": False,
                "message": f"用户未绑定 {device_type} 设备"
            }
        
        try:
            # 创建适配器
            adapter = cls.create_adapter_from_credential(credential)
            
            # 同步数据
            synced = 0
            failed = 0
            today = date.today()
            
            for i in range(days):
                target_date = today - timedelta(days=i)
                try:
                    data = await adapter.fetch_daily_data(target_date)
                    if data:
                        cls._save_health_data(db, user_id, data)
                        synced += 1
                except Exception as e:
                    logger.warning(f"同步 {target_date} 失败: {e}")
                    failed += 1
            
            # 更新同步时间
            credential.update_sync_time()
            credential.mark_valid()
            db.commit()
            
            return {
                "success": True,
                "synced_days": synced,
                "failed_days": failed,
                "message": f"同步完成：成功 {synced} 天，失败 {failed} 天"
            }
            
        except Exception as e:
            logger.error(f"设备同步失败 ({device_type}): {e}")
            credential.mark_invalid(str(e))
            db.commit()
            return {
                "success": False,
                "message": f"同步失败: {str(e)}"
            }
    
    @classmethod
    async def sync_all_devices(
        cls,
        db: Session,
        user_id: int,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        同步用户所有绑定设备的数据
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            days: 同步天数
            
        Returns:
            各设备同步结果列表
        """
        credentials = db.query(DeviceCredential).filter(
            DeviceCredential.user_id == user_id,
            DeviceCredential.is_valid == True,
            DeviceCredential.sync_enabled == True
        ).all()
        
        results = []
        for cred in credentials:
            result = await cls.sync_device_data(db, user_id, cred.device_type, days)
            result["device"] = cred.device_type
            results.append(result)
        
        return results
    
    @classmethod
    def _save_health_data(
        cls, 
        db: Session, 
        user_id: int, 
        data: NormalizedHealthData
    ):
        """
        保存健康数据到数据库
        
        注意：目前仍然保存到 GarminData 表（为了兼容）
        后续会迁移到统一的 HealthData 表
        """
        from app.models.daily_health import GarminData
        import json
        
        # 查找是否已有记录
        existing = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == data.record_date
        ).first()
        
        if existing:
            # 更新现有记录
            record = existing
        else:
            # 创建新记录
            record = GarminData(
                user_id=user_id,
                record_date=data.record_date
            )
            db.add(record)
        
        # 映射数据字段
        if data.sleep_score is not None:
            record.sleep_score = data.sleep_score
        if data.total_sleep_minutes is not None:
            record.total_sleep_duration = data.total_sleep_minutes
        if data.deep_sleep_minutes is not None:
            record.deep_sleep_duration = data.deep_sleep_minutes
        if data.rem_sleep_minutes is not None:
            record.rem_sleep_duration = data.rem_sleep_minutes
        if data.light_sleep_minutes is not None:
            record.light_sleep_duration = data.light_sleep_minutes
        if data.awake_minutes is not None:
            record.awake_duration = data.awake_minutes
            
        if data.resting_heart_rate is not None:
            record.resting_heart_rate = data.resting_heart_rate
        if data.avg_heart_rate is not None:
            record.avg_heart_rate = data.avg_heart_rate
        if data.max_heart_rate is not None:
            record.max_heart_rate = data.max_heart_rate
        if data.min_heart_rate is not None:
            record.min_heart_rate = data.min_heart_rate
            
        if data.hrv is not None:
            record.hrv = data.hrv
        if data.hrv_status is not None:
            record.hrv_status = data.hrv_status
            
        if data.steps is not None:
            record.steps = data.steps
        if data.distance_meters is not None:
            record.distance_meters = data.distance_meters
        if data.floors_climbed is not None:
            record.floors_climbed = data.floors_climbed
        if data.active_minutes is not None:
            record.active_minutes = data.active_minutes
        if data.calories_total is not None:
            record.calories_burned = data.calories_total
        if data.calories_active is not None:
            record.active_calories = data.calories_active
            
        if data.stress_level is not None:
            record.stress_level = data.stress_level
        if data.body_battery_high is not None:
            record.body_battery_most_charged = data.body_battery_high
        if data.body_battery_low is not None:
            record.body_battery_lowest = data.body_battery_low
            
        if data.spo2_avg is not None:
            record.spo2_avg = data.spo2_avg
        if data.spo2_min is not None:
            record.spo2_min = data.spo2_min
            
        if data.respiration_rate_avg is not None:
            record.avg_respiration_awake = data.respiration_rate_avg
        
        db.commit()


# ===== 注册默认适配器 =====
def _register_default_adapters():
    """注册默认的设备适配器"""
    try:
        from .huawei import HuaweiHealthAdapter
        DeviceManager.register_adapter("huawei", HuaweiHealthAdapter)
    except ImportError as e:
        logger.warning(f"华为适配器注册失败: {e}")
    
    # TODO: 后续添加更多适配器
    # from .garmin import GarminAdapter
    # DeviceManager.register_adapter("garmin", GarminAdapter)


# 模块加载时注册适配器
_register_default_adapters()
