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
    temperature: number;
    feels_like: number;
    humidity: number;
    weather: string;
    wind_direction: string;
    wind_speed: number;
  };
  air_quality: {
    available: boolean;
    aqi: number;
    level: string;
    description: string;
    pm25: number;
    health_implications: string;
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

export default function EnvironmentPage() {
  const [loading, setLoading] = useState(true);
  const [advice, setAdvice] = useState<EnvironmentAdvice | null>(null);
  const [briefing, setBriefing] = useState<MorningBriefing | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    const token = Taro.getStorageSync('token');
    if (!token) {
      Taro.switchTab({ url: '/pages/index/index' });
      return;
    }

    try {
      setLoading(true);
      const [adviceRes, briefingRes] = await Promise.all([
        request<EnvironmentAdvice>({ url: '/environment/advice', method: 'GET' }),
        request<MorningBriefing>({ url: '/environment/morning-briefing', method: 'GET' }),
      ]);
      setAdvice(adviceRes.data);
      setBriefing(briefingRes.data);
    } catch (error) {
      console.error('加载环境数据失败:', error);
      Taro.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <View className="environment-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  const weather = advice?.weather;
  const airQuality = advice?.air_quality;
  const exercise = advice?.exercise;

  return (
    <ScrollView scrollY className="environment-page">
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
              <Text className="status-label">{statusLabels[exercise.status]}</Text>
            </View>
          </View>
        </View>
      )}

      {/* 天气和空气质量 */}
      <View className="data-row">
        {/* 天气 */}
        {weather?.available && (
          <View className="data-card">
            <View className="card-header">
              <Text className="card-icon">🌡️</Text>
              <Text className="card-title">实时天气</Text>
            </View>
            <View className="weather-content">
              <View className="weather-main">
                <Text className="temperature">{Math.round(weather.temperature)}°C</Text>
                <Text className="feels-like">体感 {Math.round(weather.feels_like)}°C</Text>
              </View>
              <View className="weather-detail">
                <Text className="weather-text">{weather.weather}</Text>
                <Text className="wind">{weather.wind_direction} {weather.wind_speed}km/h</Text>
              </View>
            </View>
            <Text className="humidity">💧 湿度 {weather.humidity}%</Text>
          </View>
        )}

        {/* 空气质量 */}
        {airQuality?.available && (
          <View className="data-card">
            <View className="card-header">
              <Text className="card-icon">🌬️</Text>
              <Text className="card-title">空气质量</Text>
            </View>
            <View className="aqi-content">
              <View className="aqi-main">
                <Text className={`aqi-value ${airQuality.level}`}>{airQuality.aqi}</Text>
                <Text className="aqi-label">AQI</Text>
              </View>
              <Text className={`aqi-desc ${airQuality.level}`}>{airQuality.description}</Text>
            </View>
            <Text className="pm25">PM2.5: {airQuality.pm25} μg/m³</Text>
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

      <View className="bottom-spacer" />
    </ScrollView>
  );
}
