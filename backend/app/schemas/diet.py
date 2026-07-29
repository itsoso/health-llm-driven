"""饮食记录模式"""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Any
from datetime import date, datetime, time
import enum


class MealType(str, enum.Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    EXTRA = "extra"


class DietRecordBase(BaseModel):
    """饮食记录基础"""
    record_date: date
    meal_type: MealType
    meal_time: Optional[time] = None
    food_items: str  # 食物列表，逗号分隔
    food_id: Optional[str] = None  # 结构化食物库 ID
    source: Optional[str] = None  # 营养数据来源
    calories: Optional[float] = None  # 热量 (kcal) - 使用float与数据库一致
    protein: Optional[float] = None  # 蛋白质 (g)
    carbs: Optional[float] = None  # 碳水化合物 (g)
    fat: Optional[float] = None  # 脂肪 (g)
    fiber: Optional[float] = None  # 膳食纤维 (g)
    alcohol_units: Optional[float] = None  # 酒精标准杯数 (1 unit ≈ 14g 纯酒精)
    notes: Optional[str] = None
    ai_recognized: Optional[int] = 0  # 是否AI识别
    ai_confidence: Optional[float] = None  # AI/语音解析置信度
    ai_raw_result: Optional[Any] = None  # AI识别原始 JSON (创建时落库,响应暂不回传)
    health_tips: Optional[str] = None  # AI健康提示


class DietRecordCreate(DietRecordBase):
    """创建饮食记录"""
    user_id: Optional[int] = None  # 可选，后端会使用当前登录用户ID
    image_base64: Optional[str] = None  # 可选，Base64编码的图片数据
    image_type: Optional[str] = "jpeg"  # 图片类型
    photo_draft_token: Optional[str] = Field(
        default=None,
        min_length=24,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class DietRecordUpdate(BaseModel):
    """更新饮食记录"""
    meal_type: Optional[MealType] = None
    meal_time: Optional[time] = None
    food_items: Optional[str] = None
    food_id: Optional[str] = None
    source: Optional[str] = None
    calories: Optional[float] = None  # 使用float与数据库一致
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None
    fiber: Optional[float] = None
    alcohol_units: Optional[float] = None
    notes: Optional[str] = None
    health_tips: Optional[str] = None
    ai_recognized: Optional[int] = None
    ai_confidence: Optional[float] = None
    ai_raw_result: Optional[Any] = None


class DietPhotoDraftStatusResponse(BaseModel):
    status: str
    expires_at: datetime


class DietPhotoAssetResponse(BaseModel):
    id: str
    url: str
    ordinal: int
    captured_at: Optional[datetime] = None
    origin: str

    model_config = ConfigDict(from_attributes=True)


MEAL_TYPE_ZH = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
    "extra": "其他",
}


class DietRecordResponse(DietRecordBase):
    """饮食记录响应"""
    id: int
    user_id: int
    image_url: Optional[str] = None
    image_urls: List[str] = Field(default_factory=list)
    photo_assets: List[DietPhotoAssetResponse] = Field(default_factory=list)
    ai_confidence: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    display_message: str = ""

    model_config = ConfigDict(from_attributes=True)

    def model_post_init(self, __context: Any) -> None:
        meal_key = self.meal_type.value if hasattr(self.meal_type, "value") else str(self.meal_type)
        meal_zh = MEAL_TYPE_ZH.get(meal_key, meal_key)
        parts = [f"已记录{meal_zh}：{self.food_items}"]
        if self.calories is not None:
            parts.append(f"{int(self.calories)} 千卡")
        macros = []
        if self.protein is not None:
            macros.append(f"蛋白 {self.protein:.0f}g")
        if self.carbs is not None:
            macros.append(f"碳水 {self.carbs:.0f}g")
        if self.fat is not None:
            macros.append(f"脂肪 {self.fat:.0f}g")
        if macros:
            parts.append("（" + " / ".join(macros) + "）")
        object.__setattr__(self, "display_message", "✅ " + "，".join(parts[:2]) + ("".join(parts[2:]) if len(parts) > 2 else ""))


class DailyDietSummary(BaseModel):
    """每日饮食汇总"""
    record_date: date
    total_calories: int = 0
    total_protein: float = 0
    total_carbs: float = 0
    total_fat: float = 0
    total_fiber: float = 0
    meals_count: int = 0
    meals: List[DietRecordResponse] = []


class DietStats(BaseModel):
    """饮食统计"""
    average_daily_calories: Optional[float] = None
    average_daily_protein: Optional[float] = None
    average_daily_carbs: Optional[float] = None
    average_daily_fat: Optional[float] = None
    total_records: int = 0
    days_recorded: int = 0


class FrequentFood(BaseModel):
    """常吃食物 —— 由历史 DietRecord 按 food_items 聚合得出, 供首页/记录页一键复用.

    营养素取该食物历次记录的中位数 (历次数值可能不同), 是"按历史估算"非精确值.
    """
    food_items: str
    meal_type: MealType
    count: int  # 该食物在窗口内出现次数
    calories: Optional[float] = None
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None


# ========== AI食物识别相关 ==========

class FoodItem(BaseModel):
    """识别出的单个食物"""
    name: str
    quantity: Optional[str] = None
    calories: Optional[float] = None
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None
    fiber: Optional[float] = None
    confidence: Optional[float] = None
    food_id: Optional[str] = None
    source: Optional[str] = None
    quantity_grams: Optional[float] = None
    label_basis_grams: Optional[float] = None
    nutrition_basis: Optional[str] = None
    portion_basis: Optional[str] = None
    portion_confidence: Optional[float] = None


class FoodRecognitionRequest(BaseModel):
    """食物识别请求"""
    image_base64: str = Field(..., description="Base64编码的图片数据")
    image_type: str = Field(default="jpeg", description="图片类型: jpeg, png, gif, webp")
    create_photo_draft: bool = Field(
        default=False,
        description="识别成功后保存一次图片并返回待确认草稿令牌",
    )


class FoodRecognitionTiming(BaseModel):
    vision: int = 0
    calibration: int = 0
    photo_draft: int = 0
    total: int = 0


class FoodRecognitionResponse(BaseModel):
    """食物识别响应"""
    success: bool
    foods: List[FoodItem] = []
    meal_description: Optional[str] = None
    health_tips: Optional[str] = None
    total_calories: Optional[int] = None
    total_protein: Optional[float] = None
    total_carbs: Optional[float] = None
    total_fat: Optional[float] = None
    total_fiber: Optional[float] = None
    photo_draft_token: Optional[str] = None
    timing_ms: Optional[FoodRecognitionTiming] = None
    error: Optional[str] = None


class CreateDietFromImageRequest(BaseModel):
    """从图片创建饮食记录的请求"""
    image_base64: str = Field(..., description="Base64编码的图片数据")
    image_type: str = Field(default="jpeg", description="图片类型")
    record_date: date = Field(..., description="记录日期")
    meal_type: MealType = Field(..., description="餐食类型")
    notes: Optional[str] = None


# ── 语音食物解析(Apple Watch Companion / R5)──────────────────────
class VoiceFoodParseRequest(BaseModel):
    """语音转写文本 → 食物草稿(只解析不写库)。"""
    raw_text: str = Field(..., min_length=1, max_length=1000, description="语音转写文本")
    meal_type: Optional[MealType] = Field(None, description="餐次(不给则按文本/时刻推断)")
    source: Optional[str] = Field(None, max_length=50, description="语音来源,如 apple_watch/airpods/mobile")
    device_type: Optional[str] = Field(None, max_length=40, description="设备类型,如 watch/earbuds/mobile")


class VoiceFoodDraftItem(BaseModel):
    """单个语音食物草稿项。营养值允许为空,客户端确认后再入库。"""
    name: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    calories: Optional[float] = None
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None
    fiber: Optional[float] = None
    food_id: Optional[str] = None
    source: Optional[str] = None


class VoiceFoodParseResponse(BaseModel):
    """食物草稿。客户端确认后再 POST /diet/records 写库。"""
    raw_text: str
    meal_type: MealType
    meal_type_label: str
    foods: List[VoiceFoodDraftItem] = Field(default_factory=list)
    risk_tags: List[str] = Field(default_factory=list)
    confidence: float
    needs_confirmation: bool
    clarifying_question: Optional[str] = None
    parser_version: str
