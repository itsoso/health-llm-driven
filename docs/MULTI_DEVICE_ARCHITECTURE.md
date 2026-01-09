# 多智能设备接入架构方案

## 一、现状分析

### 1.1 当前架构问题

```
┌─────────────┐     ┌─────────────────────┐     ┌──────────────┐
│   前端/小程序  │ ──→ │  GarminConnectService │ ──→ │  GarminData  │
└─────────────┘     └─────────────────────┘     └──────────────┘
```

**问题**：
1. **紧耦合**: 数据模型直接命名为 `GarminData`，与 Garmin 设备强绑定
2. **无抽象层**: 没有统一的设备接口，新增设备需要大量改动
3. **数据不统一**: 不同设备的数据格式、字段名、单位可能不同
4. **凭证管理分散**: Garmin 凭证存储在特定表中，缺乏扩展性

### 1.2 待支持设备对比

| 设备 | 数据获取方式 | 认证方式 | 数据特点 |
|------|-------------|---------|---------|
| **Garmin** | garminconnect 库 (网页爬虫) | 账号密码 | 数据最全面，包含 HRV、身体电量等 |
| **Apple Watch** | HealthKit API / 健康导出 | 无需认证（本地数据）或 OAuth | 通过 iPhone 导出，需要用户手动操作 |
| **华为手表** | 华为运动健康 API | OAuth 2.0 | 需要申请开发者权限 |
| **小米手环** | Zepp API (原 Amazfit) | OAuth 2.0 | 数据相对简单 |
| **Fitbit** | Fitbit Web API | OAuth 2.0 | 官方 API 支持良好 |

---

## 二、目标架构设计

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                          应用层 (API)                            │
│   /daily-health/me  /heart-rate/me  /workout/me  /sync/me       │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       健康数据服务层                              │
│   HealthDataService - 统一的健康数据查询和聚合服务                  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      数据规范化层 (Normalizer)                    │
│   将不同设备的原始数据转换为统一的 HealthData 格式                   │
└─────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│ GarminAdapter │     │ AppleAdapter  │     │ HuaweiAdapter │
│   (Garmin)    │     │ (Apple Watch) │     │  (华为手表)    │
└───────────────┘     └───────────────┘     └───────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│ garminconnect │     │HealthKit/CSV  │     │ Huawei API    │
└───────────────┘     └───────────────┘     └───────────────┘
```

### 2.2 核心设计原则

1. **适配器模式**: 每个设备实现统一接口
2. **数据规范化**: 统一数据格式，屏蔽设备差异
3. **插件化架构**: 新增设备只需添加适配器，不改动核心代码
4. **多设备共存**: 用户可以绑定多个设备，数据自动合并

---

## 三、数据模型重构

### 3.1 统一健康数据模型

```python
# backend/app/models/health_data.py

from enum import Enum

class DeviceType(str, Enum):
    """支持的设备类型"""
    GARMIN = "garmin"
    APPLE = "apple"
    HUAWEI = "huawei"
    XIAOMI = "xiaomi"
    FITBIT = "fitbit"
    MANUAL = "manual"  # 手动录入


class DeviceCredential(Base):
    """设备凭证（统一管理所有设备的认证信息）"""
    __tablename__ = "device_credentials"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_type = Column(String, nullable=False)  # garmin, apple, huawei, etc.
    
    # 通用认证字段
    auth_type = Column(String)  # password, oauth, token
    encrypted_credentials = Column(Text)  # 加密存储的凭证 JSON
    
    # OAuth 相关
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_expires_at = Column(DateTime)
    
    # 状态
    is_valid = Column(Boolean, default=True)
    last_sync_at = Column(DateTime)
    sync_enabled = Column(Boolean, default=True)
    
    # 设备特定配置 (JSON)
    config = Column(Text)  # {"is_cn": true, "region": "CN"} 等
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class HealthData(Base):
    """统一健康数据模型（替代原 GarminData）"""
    __tablename__ = "health_data"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    record_date = Column(Date, nullable=False, index=True)
    
    # 数据来源
    source = Column(String, nullable=False)  # garmin, apple, huawei, manual
    source_device_id = Column(String)  # 设备唯一标识
    
    # ===== 睡眠数据 =====
    sleep_score = Column(Integer)  # 0-100
    total_sleep_minutes = Column(Integer)
    deep_sleep_minutes = Column(Integer)
    rem_sleep_minutes = Column(Integer)
    light_sleep_minutes = Column(Integer)
    awake_minutes = Column(Integer)
    sleep_start_time = Column(Time)
    sleep_end_time = Column(Time)
    
    # ===== 心率数据 =====
    resting_heart_rate = Column(Integer)
    avg_heart_rate = Column(Integer)
    max_heart_rate = Column(Integer)
    min_heart_rate = Column(Integer)
    
    # ===== HRV (心率变异性) =====
    hrv = Column(Float)
    hrv_status = Column(String)  # balanced, unbalanced, low
    
    # ===== 活动数据 =====
    steps = Column(Integer)
    distance_meters = Column(Float)
    floors_climbed = Column(Integer)
    active_minutes = Column(Integer)
    calories_total = Column(Integer)
    calories_active = Column(Integer)
    
    # ===== 压力与恢复 =====
    stress_level = Column(Integer)  # 0-100
    body_battery_high = Column(Integer)  # Garmin 特有，其他设备可能为空
    body_battery_low = Column(Integer)
    
    # ===== 血氧 =====
    spo2_avg = Column(Float)
    spo2_min = Column(Float)
    
    # ===== 呼吸 =====
    respiration_rate_avg = Column(Float)
    
    # ===== 原始数据 (JSON，保存设备特有字段) =====
    raw_data = Column(Text)  # 完整的原始数据，便于调试和扩展
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    # 复合唯一约束：同一用户同一天同一来源只有一条记录
    __table_args__ = (
        UniqueConstraint('user_id', 'record_date', 'source', name='uq_health_data_user_date_source'),
    )
```

### 3.2 数据迁移策略

```sql
-- 1. 创建新表
CREATE TABLE health_data (...);
CREATE TABLE device_credentials (...);

-- 2. 迁移 GarminData 到 HealthData
INSERT INTO health_data (user_id, record_date, source, ...)
SELECT user_id, record_date, 'garmin', ...
FROM garmin_data;

-- 3. 迁移 garmin_credentials 到 device_credentials
INSERT INTO device_credentials (user_id, device_type, ...)
SELECT user_id, 'garmin', ...
FROM garmin_credentials;

-- 4. 保留旧表一段时间，验证无误后删除
-- DROP TABLE garmin_data;
-- DROP TABLE garmin_credentials;
```

---

## 四、设备适配器设计

### 4.1 抽象基类

```python
# backend/app/services/device_adapters/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional, List, Dict, Any


@dataclass
class NormalizedHealthData:
    """规范化的健康数据（适配器输出格式）"""
    record_date: date
    
    # 睡眠
    sleep_score: Optional[int] = None
    total_sleep_minutes: Optional[int] = None
    deep_sleep_minutes: Optional[int] = None
    rem_sleep_minutes: Optional[int] = None
    light_sleep_minutes: Optional[int] = None
    
    # 心率
    resting_heart_rate: Optional[int] = None
    avg_heart_rate: Optional[int] = None
    hrv: Optional[float] = None
    
    # 活动
    steps: Optional[int] = None
    distance_meters: Optional[float] = None
    calories_active: Optional[int] = None
    
    # 压力恢复
    stress_level: Optional[int] = None
    body_battery_high: Optional[int] = None
    body_battery_low: Optional[int] = None
    
    # 血氧
    spo2_avg: Optional[float] = None
    
    # 原始数据
    raw_data: Optional[Dict[str, Any]] = None


class DeviceAdapter(ABC):
    """设备适配器抽象基类"""
    
    @property
    @abstractmethod
    def device_type(self) -> str:
        """返回设备类型标识"""
        pass
    
    @property
    @abstractmethod
    def display_name(self) -> str:
        """返回设备显示名称"""
        pass
    
    @abstractmethod
    async def authenticate(self, credentials: Dict[str, Any]) -> bool:
        """
        验证设备凭证
        
        Args:
            credentials: 凭证信息，格式因设备而异
            
        Returns:
            认证是否成功
        """
        pass
    
    @abstractmethod
    async def fetch_daily_data(self, target_date: date) -> Optional[NormalizedHealthData]:
        """
        获取指定日期的健康数据
        
        Args:
            target_date: 目标日期
            
        Returns:
            规范化的健康数据，无数据时返回 None
        """
        pass
    
    @abstractmethod
    async def fetch_heart_rate_samples(self, target_date: date) -> List[Dict[str, Any]]:
        """
        获取心率采样数据
        
        Returns:
            [{"time": "08:00", "heart_rate": 72}, ...]
        """
        pass
    
    async def fetch_workouts(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        获取运动记录（可选实现）
        """
        return []
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        测试连接
        
        Returns:
            {"success": True, "message": "连接成功", "user_info": {...}}
        """
        pass
```

### 4.2 Garmin 适配器

```python
# backend/app/services/device_adapters/garmin.py

from .base import DeviceAdapter, NormalizedHealthData
from garminconnect import Garmin


class GarminAdapter(DeviceAdapter):
    """Garmin 设备适配器"""
    
    def __init__(self, email: str, password: str, is_cn: bool = False):
        self.email = email
        self.password = password
        self.is_cn = is_cn
        self.client: Optional[Garmin] = None
    
    @property
    def device_type(self) -> str:
        return "garmin"
    
    @property
    def display_name(self) -> str:
        return "Garmin"
    
    async def authenticate(self, credentials: Dict[str, Any]) -> bool:
        try:
            self.client = Garmin(
                credentials.get("email", self.email),
                credentials.get("password", self.password),
                is_cn=credentials.get("is_cn", self.is_cn)
            )
            self.client.login()
            return True
        except Exception as e:
            logger.error(f"Garmin认证失败: {e}")
            return False
    
    async def fetch_daily_data(self, target_date: date) -> Optional[NormalizedHealthData]:
        """获取并规范化 Garmin 日常数据"""
        if not self.client:
            await self.authenticate({})
        
        # 获取原始数据
        date_str = target_date.isoformat()
        stats = self.client.get_stats(date_str)
        sleep = self.client.get_sleep_data(date_str)
        hrv = self.client.get_hrv_data(date_str)
        
        # 转换为规范化格式
        return NormalizedHealthData(
            record_date=target_date,
            sleep_score=self._extract_sleep_score(sleep),
            total_sleep_minutes=self._extract_sleep_duration(sleep),
            resting_heart_rate=stats.get("restingHeartRate"),
            steps=stats.get("totalSteps"),
            # ... 其他字段映射
            raw_data={
                "stats": stats,
                "sleep": sleep,
                "hrv": hrv
            }
        )
    
    def _extract_sleep_score(self, sleep_data: dict) -> Optional[int]:
        """从 Garmin 睡眠数据中提取睡眠评分"""
        try:
            return sleep_data.get("dailySleepDTO", {}).get("sleepScores", {}).get("overall", {}).get("value")
        except:
            return None
```

### 4.3 Apple Health 适配器

```python
# backend/app/services/device_adapters/apple.py

class AppleHealthAdapter(DeviceAdapter):
    """
    Apple Health 适配器
    
    数据获取方式：
    1. 用户从 iPhone 健康 App 导出 XML/CSV 数据
    2. 用户上传到服务器
    3. 解析并规范化数据
    
    未来可扩展：
    - 通过 HealthKit 直接读取（需要 iOS App）
    - 通过 Apple Health Records API
    """
    
    @property
    def device_type(self) -> str:
        return "apple"
    
    @property
    def display_name(self) -> str:
        return "Apple Watch"
    
    async def authenticate(self, credentials: Dict[str, Any]) -> bool:
        # Apple Health 目前不需要认证，通过文件上传获取数据
        return True
    
    async def import_from_xml(self, xml_content: str) -> List[NormalizedHealthData]:
        """从 Apple Health 导出的 XML 解析数据"""
        import xml.etree.ElementTree as ET
        
        root = ET.fromstring(xml_content)
        health_records = []
        
        # 解析心率记录
        for record in root.findall(".//Record[@type='HKQuantityTypeIdentifierHeartRate']"):
            # 解析并聚合数据
            pass
        
        return health_records
    
    async def fetch_daily_data(self, target_date: date) -> Optional[NormalizedHealthData]:
        # 从已导入的数据库中查询
        pass
```

### 4.4 华为健康适配器

```python
# backend/app/services/device_adapters/huawei.py

class HuaweiHealthAdapter(DeviceAdapter):
    """
    华为运动健康适配器
    
    认证方式：OAuth 2.0
    API 文档：https://developer.huawei.com/consumer/cn/doc/development/HMSCore-Guides/overview-0000001080746960
    
    需要：
    1. 注册华为开发者账号
    2. 创建应用并获取 Client ID 和 Client Secret
    3. 用户授权后获取 Access Token
    """
    
    HUAWEI_AUTH_URL = "https://oauth-login.cloud.huawei.com/oauth2/v3/authorize"
    HUAWEI_TOKEN_URL = "https://oauth-login.cloud.huawei.com/oauth2/v3/token"
    HUAWEI_API_BASE = "https://health-api.cloud.huawei.com"
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token: Optional[str] = None
    
    @property
    def device_type(self) -> str:
        return "huawei"
    
    @property
    def display_name(self) -> str:
        return "华为手表"
    
    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        """生成 OAuth 授权 URL"""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": "https://www.huawei.com/healthkit/activity.read https://www.huawei.com/healthkit/heartrate.read",
            "state": state
        }
        return f"{self.HUAWEI_AUTH_URL}?{urlencode(params)}"
    
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """用授权码换取 Access Token"""
        async with aiohttp.ClientSession() as session:
            async with session.post(self.HUAWEI_TOKEN_URL, data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": redirect_uri
            }) as resp:
                return await resp.json()
    
    async def fetch_daily_data(self, target_date: date) -> Optional[NormalizedHealthData]:
        """从华为健康 API 获取数据"""
        if not self.access_token:
            raise ValueError("未认证，请先完成 OAuth 授权")
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        # 获取步数
        steps_data = await self._fetch_steps(target_date, headers)
        # 获取心率
        heart_rate_data = await self._fetch_heart_rate(target_date, headers)
        # 获取睡眠
        sleep_data = await self._fetch_sleep(target_date, headers)
        
        return NormalizedHealthData(
            record_date=target_date,
            steps=steps_data.get("steps"),
            resting_heart_rate=heart_rate_data.get("resting"),
            # ... 映射其他字段
        )
```

---

## 五、设备管理服务

### 5.1 统一管理服务

```python
# backend/app/services/device_manager.py

from typing import Dict, Type
from .device_adapters.base import DeviceAdapter
from .device_adapters.garmin import GarminAdapter
from .device_adapters.apple import AppleHealthAdapter
from .device_adapters.huawei import HuaweiHealthAdapter


class DeviceManager:
    """设备管理服务 - 统一管理所有设备适配器"""
    
    # 注册的适配器类
    _adapters: Dict[str, Type[DeviceAdapter]] = {
        "garmin": GarminAdapter,
        "apple": AppleHealthAdapter,
        "huawei": HuaweiHealthAdapter,
    }
    
    @classmethod
    def register_adapter(cls, device_type: str, adapter_class: Type[DeviceAdapter]):
        """注册新的设备适配器（插件机制）"""
        cls._adapters[device_type] = adapter_class
    
    @classmethod
    def get_supported_devices(cls) -> List[Dict[str, str]]:
        """获取支持的设备列表"""
        return [
            {"type": dtype, "name": adapter_cls({}).display_name}
            for dtype, adapter_cls in cls._adapters.items()
        ]
    
    @classmethod
    def create_adapter(cls, device_type: str, credentials: Dict[str, Any]) -> DeviceAdapter:
        """根据设备类型创建适配器实例"""
        if device_type not in cls._adapters:
            raise ValueError(f"不支持的设备类型: {device_type}")
        
        adapter_class = cls._adapters[device_type]
        return adapter_class(**credentials)
    
    async def sync_user_device(
        self, 
        db: Session, 
        user_id: int, 
        device_type: str, 
        days: int = 7
    ) -> Dict[str, Any]:
        """同步用户指定设备的数据"""
        # 1. 获取用户的设备凭证
        credential = db.query(DeviceCredential).filter(
            DeviceCredential.user_id == user_id,
            DeviceCredential.device_type == device_type,
            DeviceCredential.is_valid == True
        ).first()
        
        if not credential:
            raise ValueError(f"用户未绑定 {device_type} 设备")
        
        # 2. 创建适配器
        adapter = self.create_adapter(device_type, credential.get_decrypted_credentials())
        
        # 3. 同步数据
        synced = 0
        for i in range(days):
            target_date = date.today() - timedelta(days=i)
            data = await adapter.fetch_daily_data(target_date)
            if data:
                self._save_health_data(db, user_id, device_type, data)
                synced += 1
        
        # 4. 更新同步时间
        credential.last_sync_at = datetime.now()
        db.commit()
        
        return {"synced_days": synced, "device": device_type}
    
    async def sync_all_user_devices(self, db: Session, user_id: int, days: int = 7):
        """同步用户所有绑定设备的数据"""
        credentials = db.query(DeviceCredential).filter(
            DeviceCredential.user_id == user_id,
            DeviceCredential.is_valid == True,
            DeviceCredential.sync_enabled == True
        ).all()
        
        results = []
        for cred in credentials:
            try:
                result = await self.sync_user_device(db, user_id, cred.device_type, days)
                results.append(result)
            except Exception as e:
                logger.error(f"同步 {cred.device_type} 失败: {e}")
                results.append({"device": cred.device_type, "error": str(e)})
        
        return results
```

---

## 六、API 设计

### 6.1 设备管理 API

```python
# backend/app/api/devices.py

@router.get("/supported", summary="获取支持的设备列表")
async def get_supported_devices():
    """返回系统支持的所有智能设备"""
    return DeviceManager.get_supported_devices()


@router.get("/me", summary="获取当前用户绑定的设备")
async def get_my_devices(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户绑定的所有设备"""
    credentials = db.query(DeviceCredential).filter(
        DeviceCredential.user_id == current_user.id
    ).all()
    return [
        {
            "device_type": c.device_type,
            "display_name": DeviceManager.get_display_name(c.device_type),
            "is_valid": c.is_valid,
            "sync_enabled": c.sync_enabled,
            "last_sync_at": c.last_sync_at
        }
        for c in credentials
    ]


@router.post("/{device_type}/bind", summary="绑定设备")
async def bind_device(
    device_type: str,
    credentials: DeviceCredentialCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """绑定指定类型的设备"""
    pass


@router.post("/{device_type}/sync", summary="同步设备数据")
async def sync_device(
    device_type: str,
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """同步指定设备的数据"""
    return await DeviceManager().sync_user_device(db, current_user.id, device_type, days)


@router.get("/{device_type}/oauth/authorize", summary="获取 OAuth 授权 URL")
async def get_oauth_url(
    device_type: str,
    redirect_uri: str,
    current_user: User = Depends(get_current_user_required)
):
    """
    获取 OAuth 授权 URL（华为、Fitbit 等需要）
    用户访问此 URL 完成授权后会回调到 redirect_uri
    """
    pass


@router.post("/{device_type}/oauth/callback", summary="OAuth 回调处理")
async def oauth_callback(
    device_type: str,
    code: str,
    state: str,
    db: Session = Depends(get_db)
):
    """处理 OAuth 授权回调，保存 Token"""
    pass
```

### 6.2 统一健康数据 API

```python
# backend/app/api/health_data.py

@router.get("/me", summary="获取我的健康数据")
async def get_my_health_data(
    start_date: date,
    end_date: date,
    sources: Optional[List[str]] = Query(None),  # 可选过滤数据来源
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取健康数据，支持多设备数据聚合
    
    - sources 为空时返回所有来源的数据
    - 同一天多个来源时，按优先级合并（可配置）
    """
    query = db.query(HealthData).filter(
        HealthData.user_id == current_user.id,
        HealthData.record_date >= start_date,
        HealthData.record_date <= end_date
    )
    
    if sources:
        query = query.filter(HealthData.source.in_(sources))
    
    return query.order_by(HealthData.record_date.desc()).all()
```

---

## 七、实施计划

### 第一阶段：基础重构（1-2 周）

1. **创建新数据模型**
   - `HealthData` 统一健康数据表
   - `DeviceCredential` 统一凭证表
   - 编写迁移脚本

2. **创建适配器基类**
   - 定义统一接口
   - 实现 Garmin 适配器（从现有代码迁移）

3. **API 兼容层**
   - 保持现有 `/garmin/me` 等 API 可用
   - 添加新的 `/health-data/me` API

### 第二阶段：Apple Health 支持（1 周）

1. **实现 Apple 适配器**
   - XML 导出文件解析
   - 数据规范化

2. **前端支持**
   - 添加文件上传功能
   - 添加 Apple Health 设备绑定 UI

### 第三阶段：华为健康支持（2 周）

1. **申请开发者权限**
   - 注册华为开发者账号
   - 创建应用，获取 API 密钥

2. **实现 OAuth 流程**
   - 授权 URL 生成
   - Token 换取和刷新

3. **实现数据获取**
   - 对接华为健康 API
   - 数据规范化

### 第四阶段：高级功能（持续）

1. **多设备数据合并**
   - 智能选择最优数据源
   - 数据冲突处理

2. **更多设备支持**
   - Fitbit
   - 小米手环
   - 等等

---

## 八、技术要点

### 8.1 OAuth 2.0 流程

```
┌─────────┐     ┌─────────┐     ┌─────────────┐     ┌─────────────┐
│  用户    │     │  前端    │     │   后端      │     │  设备厂商   │
└────┬────┘     └────┬────┘     └──────┬──────┘     └──────┬──────┘
     │               │                  │                   │
     │  1. 点击绑定   │                  │                   │
     │──────────────>│                  │                   │
     │               │  2. 请求授权URL   │                   │
     │               │─────────────────>│                   │
     │               │  3. 返回授权URL   │                   │
     │               │<─────────────────│                   │
     │  4. 跳转授权页 │                  │                   │
     │<──────────────│                  │                   │
     │               │                  │                   │
     │  5. 用户授权   │                  │                   │
     │─────────────────────────────────────────────────────>│
     │  6. 回调code   │                  │                   │
     │<─────────────────────────────────────────────────────│
     │               │  7. 提交code     │                   │
     │               │─────────────────>│                   │
     │               │                  │  8. 换取token     │
     │               │                  │─────────────────>│
     │               │                  │  9. 返回token     │
     │               │                  │<─────────────────│
     │               │  10. 绑定成功    │                   │
     │               │<─────────────────│                   │
```

### 8.2 数据优先级策略

当同一天有多个设备数据时，按以下规则合并：

```python
DATA_PRIORITY = {
    "sleep_score": ["garmin", "huawei", "apple"],  # Garmin 睡眠评分最准确
    "steps": ["apple", "huawei", "garmin"],         # Apple 步数计数最准
    "heart_rate": ["garmin", "apple", "huawei"],   # Garmin 心率监测最全面
    "hrv": ["garmin", "apple"],                     # HRV 仅部分设备支持
}

def merge_health_data(records: List[HealthData]) -> HealthData:
    """合并多个设备的健康数据"""
    merged = HealthData()
    for field, priority in DATA_PRIORITY.items():
        for source in priority:
            record = next((r for r in records if r.source == source), None)
            if record and getattr(record, field) is not None:
                setattr(merged, field, getattr(record, field))
                break
    return merged
```

---

## 九、风险与挑战

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 华为 API 申请困难 | 无法接入华为设备 | 提前申请，准备备选方案（文件导入） |
| Apple 数据只能导出 | 用户体验较差 | 开发 iOS App 直接读取 HealthKit |
| 第三方库不稳定 | 数据同步失败 | 增加重试机制，监控告警 |
| 数据格式变更 | 解析失败 | 版本化解析器，日志监控 |

---

## 十、总结

本方案通过**适配器模式**和**数据规范化层**，实现了：

1. **可扩展性**: 新增设备只需实现适配器接口
2. **统一性**: 所有设备数据格式统一，便于 AI 分析
3. **向后兼容**: 保持现有 API 可用，平滑迁移
4. **多设备共存**: 用户可同时绑定多个设备

建议按照实施计划分阶段推进，优先完成 Garmin 重构和 Apple Health 支持。
