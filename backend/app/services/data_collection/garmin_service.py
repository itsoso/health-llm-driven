"""Garmin数据收集服务"""
import httpx
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.models.daily_health import GarminData
from app.schemas.daily_health import GarminDataCreate
from app.config import settings


class GarminService:
    """Garmin API服务"""
    
    def __init__(self):
        self.api_key = settings.garmin_api_key
        self.api_secret = settings.garmin_api_secret
        # Garmin Connect API (需要OAuth认证)
        # 注意：Garmin官方API需要开发者账号和OAuth流程
        # 这里提供框架，实际使用时需要实现完整的OAuth认证
        self.base_url = "https://api.garmin.com"
        # 替代方案：可以使用Garmin Connect导出数据或第三方库
    
    async def fetch_daily_data(
        self,
        user_id: int,
        target_date: date,
        access_token: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        从Garmin API获取每日数据
        
        注意：Garmin API需要OAuth认证，这里提供框架代码
        实际使用时需要实现完整的OAuth流程
        """
        if not access_token:
            # 如果没有access_token，返回None，提示需要认证
            return None
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                # 获取每日活动数据
                activity_url = f"{self.base_url}/wellness-api/rest/dailySummary"
                params = {
                    "calendarDate": target_date.isoformat()
                }
                response = await client.get(activity_url, headers=headers, params=params)
                
                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"Garmin API错误: {response.status_code}")
                    return None
        except Exception as e:
            print(f"获取Garmin数据失败: {str(e)}")
            return None
    
    def parse_garmin_data(
        self,
        raw_data: Dict[str, Any],
        user_id: int,
        record_date: date
    ) -> GarminDataCreate:
        """解析Garmin API返回的原始数据"""
        return GarminDataCreate(
            user_id=user_id,
            record_date=record_date,
            avg_heart_rate=raw_data.get("averageHeartRate"),
            max_heart_rate=raw_data.get("maxHeartRate"),
            min_heart_rate=raw_data.get("minHeartRate"),
            resting_heart_rate=raw_data.get("restingHeartRate"),
            hrv=raw_data.get("hrv"),
            sleep_score=raw_data.get("sleepScore"),
            total_sleep_duration=raw_data.get("sleepDurationSeconds", 0) // 60 if raw_data.get("sleepDurationSeconds") else None,
            deep_sleep_duration=raw_data.get("deepSleepSeconds", 0) // 60 if raw_data.get("deepSleepSeconds") else None,
            rem_sleep_duration=raw_data.get("remSleepSeconds", 0) // 60 if raw_data.get("remSleepSeconds") else None,
            light_sleep_duration=raw_data.get("lightSleepSeconds", 0) // 60 if raw_data.get("lightSleepSeconds") else None,
            awake_duration=raw_data.get("awakeSleepSeconds", 0) // 60 if raw_data.get("awakeSleepSeconds") else None,
            body_battery_charged=raw_data.get("bodyBatteryCharged"),
            body_battery_drained=raw_data.get("bodyBatteryDrained"),
            body_battery_most_charged=raw_data.get("bodyBatteryMostCharged"),
            body_battery_lowest=raw_data.get("bodyBatteryLowest"),
            stress_level=raw_data.get("stressLevel"),
            steps=raw_data.get("steps"),
            calories_burned=raw_data.get("caloriesBurned"),
            active_minutes=raw_data.get("activeMinutes"),
        )
    
    def save_garmin_data(
        self,
        db: Session,
        garmin_data: GarminDataCreate
    ) -> GarminData:
        """保存Garmin数据到数据库"""
        # 检查是否已存在该日期的记录
        existing = db.query(GarminData).filter(
            GarminData.user_id == garmin_data.user_id,
            GarminData.record_date == garmin_data.record_date
        ).first()
        
        if existing:
            # 更新现有记录
            for key, value in garmin_data.model_dump(exclude={"user_id", "record_date"}).items():
                if value is not None:
                    setattr(existing, key, value)
            db.commit()
            db.refresh(existing)
            return existing
        else:
            # 创建新记录
            db_garmin = GarminData(**garmin_data.model_dump())
            db.add(db_garmin)
            db.commit()
            db.refresh(db_garmin)
            return db_garmin
    
    async def sync_garmin_data(
        self,
        db: Session,
        user_id: int,
        target_date: date,
        access_token: Optional[str] = None
    ) -> Optional[GarminData]:
        """
        同步Garmin数据
        
        完整的流程：
        1. 从Garmin API获取数据
        2. 解析数据
        3. 保存到数据库
        """
        raw_data = await self.fetch_daily_data(user_id, target_date, access_token)
        
        if not raw_data:
            return None
        
        garmin_data = self.parse_garmin_data(raw_data, user_id, target_date)
        return self.save_garmin_data(db, garmin_data)


class DataCollectionService:
    """数据收集服务主类"""
    
    def __init__(self):
        self.garmin_service = GarminService()
    
    async def sync_garmin_data(
        self,
        db: Session,
        user_id: int,
        target_date: date,
        access_token: Optional[str] = None
    ) -> Optional[GarminData]:
        """同步Garmin数据"""
        return await self.garmin_service.sync_garmin_data(
            db, user_id, target_date, access_token
        )

