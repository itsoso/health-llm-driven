"""
环境数据服务模块

提供天气、空气质量等环境数据，用于：
- 生成个性化健康建议（如雾霾天减少户外运动）
- 疾病管理（如花粉季节鼻炎预警）
- 运动建议优化
"""

from .weather_service import WeatherService, weather_service
from .air_quality_service import AirQualityService, air_quality_service
from .environment_advisor import EnvironmentAdvisor, environment_advisor

__all__ = [
    'WeatherService', 'weather_service',
    'AirQualityService', 'air_quality_service', 
    'EnvironmentAdvisor', 'environment_advisor'
]
