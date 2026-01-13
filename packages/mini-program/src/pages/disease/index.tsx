import { useState, useEffect, useCallback } from 'react';
import { View, Text, ScrollView, Slider } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { request } from '../../services/request';
import './index.scss';

interface DiseaseTemplate {
  id: number;
  name: string;
  display_name: string;
  category: string;
  icon: string;
  symptoms: string[];
}

interface DiseaseProfile {
  id: number;
  disease_name: string;
  severity: string;
  status: string;
  current_streak: number;
  best_streak: number;
  template: {
    name: string;
    display_name: string;
    icon: string;
  } | null;
}

interface SymptomStats {
  avg_severity: number;
  symptom_free_days: number;
  symptom_free_rate: number;
  total_logs: number;
  daily_trend: { date: string; severity: number }[];
}

interface EnvironmentAlert {
  alert_level: string;
  warnings: string[];
  recommendations: string[];
  environment: {
    weather: string;
    temperature: number;
    aqi: number;
    aqi_description: string;
  };
}

const severityLabels: Record<string, string> = {
  mild: '轻度',
  moderate: '中度',
  severe: '重度',
};

const statusLabels: Record<string, string> = {
  chronic: '慢性',
  improving: '好转中',
  controlled: '已控制',
  cured: '已治愈',
};

const categoryLabels: Record<string, string> = {
  respiratory: '呼吸系统',
  vision: '视力',
  cardiovascular: '心血管',
  metabolic: '代谢',
};

export default function DiseasePage() {
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState<DiseaseTemplate[]>([]);
  const [profiles, setProfiles] = useState<DiseaseProfile[]>([]);
  const [activeTab, setActiveTab] = useState<'profiles' | 'templates'>('profiles');
  const [selectedProfile, setSelectedProfile] = useState<DiseaseProfile | null>(null);
  const [stats, setStats] = useState<SymptomStats | null>(null);
  const [alert, setAlert] = useState<EnvironmentAlert | null>(null);
  const [showLogModal, setShowLogModal] = useState(false);
  const [logSeverity, setLogSeverity] = useState(0);
  const [logNotes, setLogNotes] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadData = useCallback(async () => {
    const token = Taro.getStorageSync('token');
    if (!token) {
      Taro.redirectTo({ url: '/pages/index/index' });
      return;
    }

    try {
      setLoading(true);
      const [templatesRes, profilesRes] = await Promise.all([
        request<DiseaseTemplate[]>({ url: '/disease/templates', method: 'GET' }),
        request<DiseaseProfile[]>({ url: '/disease/profiles', method: 'GET' }),
      ]);
      setTemplates(templatesRes.data || []);
      setProfiles(profilesRes.data || []);
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 加载档案详情
  const loadProfileDetails = async (profile: DiseaseProfile) => {
    setSelectedProfile(profile);
    try {
      const [statsRes, alertRes] = await Promise.all([
        request<SymptomStats>({ url: `/disease/profiles/${profile.id}/stats`, method: 'GET' }),
        request<EnvironmentAlert>({ url: `/disease/profiles/${profile.id}/alert`, method: 'GET' }),
      ]);
      setStats(statsRes.data);
      setAlert(alertRes.data);
    } catch (error) {
      console.error('加载详情失败:', error);
    }
  };

  // 初始化模板
  const initTemplates = async () => {
    try {
      Taro.showLoading({ title: '初始化中...' });
      await request({ url: '/disease/templates/init', method: 'POST' });
      Taro.showToast({ title: '初始化成功', icon: 'success' });
      loadData();
    } catch (error) {
      Taro.showToast({ title: '初始化失败', icon: 'none' });
    } finally {
      Taro.hideLoading();
    }
  };

  // 添加档案
  const addProfile = async (template: DiseaseTemplate) => {
    try {
      Taro.showLoading({ title: '添加中...' });
      await request({
        url: '/disease/profiles',
        method: 'POST',
        data: {
          disease_name: template.display_name,
          template_name: template.name,
        },
      });
      Taro.showToast({ title: '添加成功', icon: 'success' });
      setActiveTab('profiles');
      loadData();
    } catch (error) {
      Taro.showToast({ title: '添加失败', icon: 'none' });
    } finally {
      Taro.hideLoading();
    }
  };

  // 记录症状
  const logSymptoms = async () => {
    if (!selectedProfile || isSubmitting) return;

    try {
      setIsSubmitting(true);
      await request({
        url: `/disease/profiles/${selectedProfile.id}/symptoms`,
        method: 'POST',
        data: {
          log_date: new Date().toISOString().split('T')[0],
          overall_severity: logSeverity,
          notes: logNotes,
          symptoms: [],
          triggers: [],
          treatments: [],
        },
      });
      Taro.showToast({ title: '记录成功', icon: 'success' });
      setShowLogModal(false);
      setLogSeverity(0);
      setLogNotes('');
      loadProfileDetails(selectedProfile);
      loadData();
    } catch (error) {
      Taro.showToast({ title: '记录失败', icon: 'none' });
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) {
    return (
      <View className="disease-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  return (
    <View className="disease-page">
      {/* Tab 切换 */}
      {!selectedProfile && (
        <View className="tab-bar">
          <View
            className={`tab-item ${activeTab === 'profiles' ? 'active' : ''}`}
            onClick={() => setActiveTab('profiles')}
          >
            <Text>📋 我的档案</Text>
          </View>
          <View
            className={`tab-item ${activeTab === 'templates' ? 'active' : ''}`}
            onClick={() => setActiveTab('templates')}
          >
            <Text>📚 疾病模板</Text>
          </View>
        </View>
      )}

      {/* 我的档案 */}
      {activeTab === 'profiles' && !selectedProfile && (
        <ScrollView scrollY className="content-scroll">
          {profiles.length > 0 ? (
            <View className="profile-list">
              {profiles.map(profile => (
                <View
                  key={profile.id}
                  className="profile-card"
                  onClick={() => loadProfileDetails(profile)}
                >
                  <View className="profile-header">
                    <View className="profile-info">
                      <Text className="profile-icon">{profile.template?.icon || '🏥'}</Text>
                      <View className="profile-text">
                        <Text className="profile-name">{profile.disease_name}</Text>
                        <Text className="profile-meta">
                          {severityLabels[profile.severity]} · {statusLabels[profile.status]}
                        </Text>
                      </View>
                    </View>
                  </View>
                  <View className="profile-stats">
                    <Text className="stat-item">🔥 连续 {profile.current_streak} 天无症状</Text>
                    <Text className="stat-item">⭐ 最佳 {profile.best_streak} 天</Text>
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <View className="empty-state">
              <Text className="empty-icon">📋</Text>
              <Text className="empty-title">暂无疾病档案</Text>
              <View className="empty-btn" onClick={() => setActiveTab('templates')}>
                添加疾病档案
              </View>
            </View>
          )}
        </ScrollView>
      )}

      {/* 档案详情 */}
      {selectedProfile && (
        <ScrollView scrollY className="content-scroll">
          <View className="back-btn" onClick={() => { setSelectedProfile(null); setStats(null); setAlert(null); }}>
            <Text>← 返回列表</Text>
          </View>

          {/* 档案信息 */}
          <View className="detail-card">
            <View className="detail-header">
              <Text className="detail-icon">{selectedProfile.template?.icon || '🏥'}</Text>
              <View className="detail-info">
                <Text className="detail-name">{selectedProfile.disease_name}</Text>
                <Text className="detail-meta">
                  {severityLabels[selectedProfile.severity]} · {statusLabels[selectedProfile.status]}
                </Text>
              </View>
            </View>

            <View className="stats-row">
              <View className="stat-box">
                <Text className="stat-value green">{selectedProfile.current_streak}</Text>
                <Text className="stat-label">连续无症状</Text>
              </View>
              <View className="stat-box">
                <Text className="stat-value yellow">{selectedProfile.best_streak}</Text>
                <Text className="stat-label">最佳记录</Text>
              </View>
              <View className="stat-box">
                <Text className="stat-value">{stats?.total_logs || 0}</Text>
                <Text className="stat-label">总记录</Text>
              </View>
            </View>

            <View className="log-btn" onClick={() => setShowLogModal(true)}>
              <Text>📝 记录今日症状</Text>
            </View>
          </View>

          {/* 环境预警 */}
          {alert && alert.alert_level !== 'none' && (
            <View className={`alert-card ${alert.alert_level}`}>
              <View className="alert-header">
                <Text className="alert-icon">⚠️</Text>
                <Text className="alert-title">环境预警</Text>
              </View>
              <View className="alert-env">
                <Text className="env-text">
                  {alert.environment.weather} {alert.environment.temperature}°C · 
                  空气{alert.environment.aqi_description} (AQI {alert.environment.aqi})
                </Text>
              </View>
              {alert.warnings.length > 0 && (
                <View className="alert-warnings">
                  {alert.warnings.map((w, i) => (
                    <Text key={i} className="warning-text">• {w}</Text>
                  ))}
                </View>
              )}
              {alert.recommendations.length > 0 && (
                <View className="alert-recommendations">
                  <Text className="rec-title">建议:</Text>
                  {alert.recommendations.slice(0, 3).map((r, i) => (
                    <Text key={i} className="rec-text">• {r}</Text>
                  ))}
                </View>
              )}
            </View>
          )}

          {/* 统计 */}
          {stats && stats.total_logs > 0 && (
            <View className="stats-card">
              <Text className="card-title">近30天统计</Text>
              <View className="stats-grid">
                <View className="stat-item">
                  <Text className="stat-num">{stats.avg_severity}</Text>
                  <Text className="stat-desc">平均严重度</Text>
                </View>
                <View className="stat-item">
                  <Text className="stat-num green">{stats.symptom_free_days}</Text>
                  <Text className="stat-desc">无症状天数</Text>
                </View>
                <View className="stat-item">
                  <Text className="stat-num">{stats.symptom_free_rate}%</Text>
                  <Text className="stat-desc">无症状率</Text>
                </View>
              </View>

              {/* 趋势图 */}
              {stats.daily_trend.length > 0 && (
                <View className="trend-chart">
                  <Text className="chart-title">症状趋势</Text>
                  <View className="chart-bars">
                    {stats.daily_trend.slice(-10).map((day, i) => (
                      <View key={i} className="chart-bar-wrapper">
                        <View
                          className={`chart-bar ${
                            day.severity === 0 ? 'green' :
                            day.severity <= 3 ? 'yellow' :
                            day.severity <= 6 ? 'orange' : 'red'
                          }`}
                          style={{ height: `${Math.max(day.severity * 10, 5)}%` }}
                        />
                        <Text className="bar-label">{new Date(day.date).getDate()}</Text>
                      </View>
                    ))}
                  </View>
                </View>
              )}
            </View>
          )}

          <View className="bottom-spacer" />
        </ScrollView>
      )}

      {/* 疾病模板 */}
      {activeTab === 'templates' && !selectedProfile && (
        <ScrollView scrollY className="content-scroll">
          {templates.length > 0 ? (
            <View className="template-list">
              {templates.map(template => (
                <View key={template.id} className="template-card">
                  <View className="template-header">
                    <Text className="template-icon">{template.icon}</Text>
                    <View className="template-info">
                      <Text className="template-name">{template.display_name}</Text>
                      <Text className="template-category">{categoryLabels[template.category]}</Text>
                    </View>
                  </View>
                  <View className="template-symptoms">
                    {template.symptoms.slice(0, 4).map((s, i) => (
                      <Text key={i} className="symptom-tag">{s}</Text>
                    ))}
                  </View>
                  <View className="add-btn" onClick={() => addProfile(template)}>
                    <Text>添加到我的档案</Text>
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <View className="empty-state">
              <Text className="empty-icon">📚</Text>
              <Text className="empty-title">暂无疾病模板</Text>
              <View className="empty-btn" onClick={initTemplates}>
                初始化默认模板
              </View>
            </View>
          )}
        </ScrollView>
      )}

      {/* 记录弹窗 */}
      {showLogModal && selectedProfile && (
        <View className="modal-mask" onClick={() => setShowLogModal(false)}>
          <View className="modal-content" onClick={e => e.stopPropagation()}>
            <Text className="modal-title">📝 记录症状 - {selectedProfile.disease_name}</Text>

            <View className="severity-section">
              <Text className="input-label">总体严重程度 (0-10)</Text>
              <View className="severity-row">
                <Slider
                  min={0}
                  max={10}
                  step={1}
                  value={logSeverity}
                  onChange={e => setLogSeverity(e.detail.value)}
                  activeColor="#9333ea"
                  backgroundColor="rgba(255,255,255,0.2)"
                  className="severity-slider"
                />
                <Text className={`severity-value ${
                  logSeverity === 0 ? 'green' :
                  logSeverity <= 3 ? 'yellow' :
                  logSeverity <= 6 ? 'orange' : 'red'
                }`}>
                  {logSeverity}
                </Text>
              </View>
              <Text className="severity-hint">0 = 无症状，10 = 非常严重</Text>
            </View>

            <View className="modal-actions">
              <View className="modal-btn cancel" onClick={() => setShowLogModal(false)}>
                <Text>取消</Text>
              </View>
              <View
                className={`modal-btn confirm ${isSubmitting ? 'disabled' : ''}`}
                onClick={logSymptoms}
              >
                <Text>{isSubmitting ? '提交中...' : '确认记录'}</Text>
              </View>
            </View>
          </View>
        </View>
      )}
    </View>
  );
}
