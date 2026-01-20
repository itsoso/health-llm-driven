import { useState, useEffect } from 'react';
import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { request } from '../../services/request';
import './index.scss';

interface EnvironmentAdvice {
  timestamp: string;
  location: string;
  weather: {
    available: boolean;
    temperature?: number;
    feels_like?: number;
    humidity?: number;
    weather?: string;
    wind_direction?: string;
    wind_speed?: number;
    summary?: string;
  };
  air_quality: {
    available: boolean;
    aqi?: number;
    level?: string;
    description?: string;
    pm25?: number;
    health_implications?: string;
  };
  exercise: {
    outdoor_suitable: boolean;
    score: number;
    status: string;
    recommended_activities: string[];
  };
  advices: string[];
  warnings: string[];
}

interface MorningBriefing {
  briefing: string;
  outdoor_score: number;
  key_advice: string;
}

const statusLabels: Record<string, string> = {
  excellent: '非常适宜',
  good: '适宜',
  moderate: '一般',
  poor: '较差',
  not_recommended: '不建议',
};

// 常用城市列表
const COMMON_CITIES = [
  '北京', '上海', '广州', '深圳', '杭州', '成都', '重庆', '武汉',
  '西安', '南京', '天津', '苏州', '郑州', '长沙', '沈阳', '青岛',
  '宁波', '厦门', '济南', '哈尔滨', '福州', '昆明', '兰州', '石家庄'
];

export default function EnvironmentPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [advice, setAdvice] = useState<EnvironmentAdvice | null>(null);
  const [briefing, setBriefing] = useState<MorningBriefing | null>(null);
  const [currentCity, setCurrentCity] = useState<string>('');
  const [showCityPicker, setShowCityPicker] = useState(false);

  useEffect(() => {
    // 从本地存储加载城市，如果没有则使用默认城市
    const savedCity = Taro.getStorageSync('selected_city') || '北京';
    setCurrentCity(savedCity);
    loadData(savedCity);
  }, []);

  const loadData = async (city?: string) => {
    const token = Taro.getStorageSync('access_token');
    if (!token) {
      setLoading(false);
      setError('请先登录');
      return;
    }

    const targetCity = city || currentCity || '北京';

    try {
      setLoading(true);
      setError(null);
      
      // 分开请求，避免一个失败导致全部失败
      let adviceData: EnvironmentAdvice | null = null;
      let briefingData: MorningBriefing | null = null;
      
      try {
        adviceData = await request<EnvironmentAdvice>({ 
          url: '/environment/advice', 
          method: 'GET',
          params: { city: targetCity }
        });
      } catch (e) {
        console.error('获取环境建议失败:', e);
      }
      
      try {
        briefingData = await request<MorningBriefing>({ 
          url: '/environment/morning-briefing', 
          method: 'GET',
          params: { city: targetCity }
        });
      } catch (e) {
        console.error('获取早间简报失败:', e);
      }
      
      if (!adviceData && !briefingData) {
        setError('无法获取环境数据，请检查网络连接');
      } else {
        setAdvice(adviceData);
        setBriefing(briefingData);
      }
    } catch (err) {
      console.error('加载环境数据失败:', err);
      setError('加载失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };
  
  const handleRefresh = () => {
    loadData();
  };

  const handleCityChange = (city: string) => {
    setCurrentCity(city);
    setShowCityPicker(false);
    // 保存到本地存储
    Taro.setStorageSync('selected_city', city);
    // 重新加载数据
    loadData(city);
  };

  if (loading) {
    return (
      <View className="environment-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }
  
  // 错误状态
  if (error) {
    return (
      <View className="environment-page error-state">
        <Text className="error-icon">😔</Text>
        <Text className="error-text">{error}</Text>
        <View className="retry-btn" onClick={handleRefresh}>
          <Text className="retry-text">点击重试</Text>
        </View>
      </View>
    );
  }

  const weather = advice?.weather;
  const airQuality = advice?.air_quality;
  const exercise = advice?.exercise;
  
  // 空状态
  if (!advice && !briefing) {
    return (
      <View className="environment-page empty-state">
        <Text className="empty-icon">🌤️</Text>
        <Text className="empty-text">暂无环境数据</Text>
        <View className="retry-btn" onClick={handleRefresh}>
          <Text className="retry-text">刷新</Text>
        </View>
      </View>
    );
  }

  return (
    <ScrollView scrollY className="environment-page">
      {/* 页面标题 */}
      <View className="page-header">
        <Text className="page-title">🌍 环境健康</Text>
        <Text className="page-subtitle">实时环境数据与健康建议</Text>
      </View>

      {/* 城市选择器 */}
      <View className="city-selector">
        <View className="current-city" onClick={() => setShowCityPicker(!showCityPicker)}>
          <Text className="city-icon">📍</Text>
          <Text className="city-name">{currentCity || '选择城市'}</Text>
          <Text className="city-arrow">{showCityPicker ? '▲' : '▼'}</Text>
        </View>
        
        {showCityPicker && (
          <View className="city-list">
            {COMMON_CITIES.map((city) => (
              <View 
                key={city} 
                className={`city-item ${city === currentCity ? 'active' : ''}`}
                onClick={() => handleCityChange(city)}
              >
                <Text className="city-item-text">{city}</Text>
                {city === currentCity && <Text className="city-check">✓</Text>}
              </View>
            ))}
          </View>
        )}
      </View>
      
      {/* 户外运动评分 */}
      {exercise && (
        <View className={`score-card ${exercise.status}`}>
          <View className="score-header">
            <View className="score-info">
              <Text className="score-label">户外运动适宜度</Text>
              <View className="score-value">
                <Text className="score-number">{exercise.score}</Text>
                <Text className="score-total">/ 100</Text>
              </View>
              <Text className="score-status">
                {exercise.outdoor_suitable ? '✅ 适合户外运动' : '❌ 建议室内运动'}
              </Text>
            </View>
            <View className="score-icon">
              <Text className="icon-emoji">
                {exercise.score >= 80 ? '🏃' : exercise.score >= 60 ? '🚶' : exercise.score >= 40 ? '🏠' : '⚠️'}
              </Text>
              <Text className="status-label">{statusLabels[exercise.status] || '未知'}</Text>
            </View>
          </View>
        </View>
      )}

      {/* 天气和空气质量 */}
      <View className="data-row">
        {/* 天气 */}
        {weather?.available ? (
          <View className="data-card">
            <View className="card-header">
              <Text className="card-icon">🌡️</Text>
              <Text className="card-title">实时天气</Text>
            </View>
            <View className="weather-content">
              <View className="weather-main">
                <Text className="temperature">{Math.round(weather.temperature || 0)}°C</Text>
                <Text className="feels-like">体感 {Math.round(weather.feels_like || 0)}°C</Text>
              </View>
              <View className="weather-detail">
                <Text className="weather-text">{weather.weather || '未知'}</Text>
                {weather.wind_direction && (
                  <Text className="wind">{weather.wind_direction} {weather.wind_speed || 0}km/h</Text>
                )}
              </View>
            </View>
            <Text className="humidity">💧 湿度 {weather.humidity || 0}%</Text>
          </View>
        ) : (
          <View className="data-card unavailable">
            <View className="card-header">
              <Text className="card-icon">🌡️</Text>
              <Text className="card-title">实时天气</Text>
            </View>
            <Text className="unavailable-text">暂无数据</Text>
          </View>
        )}

        {/* 空气质量 */}
        {airQuality?.available ? (
          <View className="data-card">
            <View className="card-header">
              <Text className="card-icon">🌬️</Text>
              <Text className="card-title">空气质量</Text>
            </View>
            <View className="aqi-content">
              <View className="aqi-main">
                <Text className={`aqi-value ${airQuality.level || ''}`}>{airQuality.aqi || 0}</Text>
                <Text className="aqi-label">AQI</Text>
              </View>
              <Text className={`aqi-desc ${airQuality.level || ''}`}>{airQuality.description || '未知'}</Text>
            </View>
            <Text className="pm25">PM2.5: {airQuality.pm25 || 0} μg/m³</Text>
          </View>
        ) : (
          <View className="data-card unavailable">
            <View className="card-header">
              <Text className="card-icon">🌬️</Text>
              <Text className="card-title">空气质量</Text>
            </View>
            <Text className="unavailable-text">暂无数据</Text>
          </View>
        )}
      </View>

      {/* 健康建议 */}
      {advice?.advices && advice.advices.length > 0 && (
        <View className="advice-section">
          <View className="section-header">
            <Text className="section-icon">💡</Text>
            <Text className="section-title">健康建议</Text>
          </View>
          <View className="advice-list">
            {advice.advices.map((item, index) => (
              <View key={index} className="advice-item">
                <Text className="advice-dot">•</Text>
                <Text className="advice-text">{item}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* 警告 */}
      {advice?.warnings && advice.warnings.length > 0 && (
        <View className="warning-section">
          <View className="section-header">
            <Text className="section-icon">⚠️</Text>
            <Text className="section-title">注意事项</Text>
          </View>
          <View className="warning-list">
            {advice.warnings.map((item, index) => (
              <View key={index} className="warning-item">
                <Text className="warning-text">{item}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* 推荐活动 */}
      {exercise?.recommended_activities && exercise.recommended_activities.length > 0 && (
        <View className="activities-section">
          <View className="section-header">
            <Text className="section-icon">🏋️</Text>
            <Text className="section-title">推荐活动</Text>
          </View>
          <View className="activities-list">
            {exercise.recommended_activities.map((activity, index) => (
              <Text key={index} className="activity-tag">{activity}</Text>
            ))}
          </View>
        </View>
      )}

      {/* 早间简报 */}
      {briefing && (
        <View className="briefing-section">
          <View className="section-header">
            <Text className="section-icon">🌅</Text>
            <Text className="section-title">早间健康简报</Text>
          </View>
          <Text className="briefing-text">{briefing.briefing}</Text>
          <View className="key-advice">
            <Text className="key-advice-text">💡 {briefing.key_advice}</Text>
          </View>
        </View>
      )}
      
      {/* 刷新按钮 */}
      <View className="refresh-section">
        <View className="refresh-btn" onClick={handleRefresh}>
          <Text className="refresh-icon">🔄</Text>
          <Text className="refresh-text">刷新数据</Text>
        </View>
      </View>

      <View className="bottom-spacer" />
    </ScrollView>
  );
}
