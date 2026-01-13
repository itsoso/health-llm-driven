'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api';

interface DiseaseTemplate {
  id: number;
  name: string;
  display_name: string;
  category: string;
  icon: string;
  symptoms: string[];
  triggers: string[];
  environment_sensitive: boolean;
  daily_tips: string[];
}

interface DiseaseProfile {
  id: number;
  disease_name: string;
  diagnosis_date: string | null;
  severity: string;
  status: string;
  tracking_enabled: boolean;
  current_streak: number;
  best_streak: number;
  template: {
    name: string;
    display_name: string;
    icon: string;
  } | null;
}

interface SymptomStats {
  period_days: number;
  total_logs: number;
  avg_severity: number;
  symptom_free_days: number;
  symptom_free_rate: number;
  top_symptoms: [string, number][];
  top_triggers: [string, number][];
  severity_distribution: Record<string, number>;
  daily_trend: { date: string; severity: number }[];
}

interface EnvironmentAlert {
  disease_name: string;
  alert_level: string;
  warnings: string[];
  recommendations: string[];
  environment: {
    weather: string;
    temperature: number;
    humidity: number;
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
  digestive: '消化系统',
  skin: '皮肤',
  mental: '心理',
  other: '其他',
};

const alertColors: Record<string, string> = {
  low: 'bg-green-500/20 border-green-500/30 text-green-300',
  moderate: 'bg-yellow-500/20 border-yellow-500/30 text-yellow-300',
  high: 'bg-red-500/20 border-red-500/30 text-red-300',
};

export default function DiseasePage() {
  const router = useRouter();
  const { user, isLoading: authLoading } = useAuth();
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<'profiles' | 'templates' | 'log'>('profiles');
  const [selectedProfile, setSelectedProfile] = useState<DiseaseProfile | null>(null);
  const [showLogModal, setShowLogModal] = useState(false);
  const [logData, setLogData] = useState({
    overall_severity: 0,
    symptoms: [] as { name: string; severity: number }[],
    triggers: [] as string[],
    treatments: [] as string[],
    notes: '',
  });

  // 获取疾病模板
  const { data: templates } = useQuery<DiseaseTemplate[]>({
    queryKey: ['diseaseTemplates'],
    queryFn: async () => {
      const response = await api.get('/disease/templates');
      return response.data;
    },
    enabled: !!user,
  });

  // 获取用户疾病档案
  const { data: profiles, isLoading: profilesLoading } = useQuery<DiseaseProfile[]>({
    queryKey: ['diseaseProfiles'],
    queryFn: async () => {
      const response = await api.get('/disease/profiles');
      return response.data;
    },
    enabled: !!user,
  });

  // 获取症状统计
  const { data: stats } = useQuery<SymptomStats>({
    queryKey: ['symptomStats', selectedProfile?.id],
    queryFn: async () => {
      const response = await api.get(`/disease/profiles/${selectedProfile?.id}/stats`);
      return response.data;
    },
    enabled: !!selectedProfile,
  });

  // 获取环境预警
  const { data: alert } = useQuery<EnvironmentAlert>({
    queryKey: ['diseaseAlert', selectedProfile?.id],
    queryFn: async () => {
      const response = await api.get(`/disease/profiles/${selectedProfile?.id}/alert`);
      return response.data;
    },
    enabled: !!selectedProfile,
  });

  // 初始化模板
  const initMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/disease/templates/init');
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['diseaseTemplates'] });
      window.alert('初始化成功');
    },
  });

  // 创建疾病档案
  const createProfileMutation = useMutation({
    mutationFn: async (data: { disease_name: string; template_name: string }) => {
      const response = await api.post('/disease/profiles', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['diseaseProfiles'] });
      setActiveTab('profiles');
    },
  });

  // 记录症状
  const logSymptomsMutation = useMutation({
    mutationFn: async (data: any) => {
      const response = await api.post(`/disease/profiles/${selectedProfile?.id}/symptoms`, {
        log_date: new Date().toISOString().split('T')[0],
        ...data,
      });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['symptomStats'] });
      queryClient.invalidateQueries({ queryKey: ['diseaseProfiles'] });
      setShowLogModal(false);
      setLogData({
        overall_severity: 0,
        symptoms: [],
        triggers: [],
        treatments: [],
        notes: '',
      });
    },
  });

  if (authLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-400"></div>
      </div>
    );
  }

  if (!user) {
    router.push('/login');
    return null;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      <main className="max-w-6xl mx-auto px-4 py-8 pt-24">
        {/* 页面标题 */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">🏥 疾病管理</h1>
          <p className="text-white/60">追踪慢性病症状，获取环境预警</p>
        </div>

        {/* Tab 切换 */}
        <div className="flex gap-2 bg-white/5 rounded-xl p-1 mb-6">
          <button
            onClick={() => { setActiveTab('profiles'); setSelectedProfile(null); }}
            className={`flex-1 py-3 rounded-lg font-medium transition-all ${
              activeTab === 'profiles'
                ? 'bg-purple-600 text-white'
                : 'text-white/70 hover:text-white hover:bg-white/10'
            }`}
          >
            📋 我的档案
          </button>
          <button
            onClick={() => setActiveTab('templates')}
            className={`flex-1 py-3 rounded-lg font-medium transition-all ${
              activeTab === 'templates'
                ? 'bg-purple-600 text-white'
                : 'text-white/70 hover:text-white hover:bg-white/10'
            }`}
          >
            📚 疾病模板
          </button>
          <button
            onClick={() => setActiveTab('log')}
            className={`flex-1 py-3 rounded-lg font-medium transition-all ${
              activeTab === 'log'
                ? 'bg-purple-600 text-white'
                : 'text-white/70 hover:text-white hover:bg-white/10'
            }`}
          >
            📝 症状记录
          </button>
        </div>

        {/* 我的档案 Tab */}
        {activeTab === 'profiles' && !selectedProfile && (
          <div className="space-y-6">
            {profilesLoading ? (
              <div className="text-center py-12">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-400 mx-auto"></div>
              </div>
            ) : profiles && profiles.length > 0 ? (
              <div className="grid md:grid-cols-2 gap-4">
                {profiles.map(profile => (
                  <div
                    key={profile.id}
                    onClick={() => setSelectedProfile(profile)}
                    className="bg-white/5 backdrop-blur rounded-xl p-6 border border-white/10 hover:bg-white/10 cursor-pointer transition-all"
                  >
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <span className="text-4xl">{profile.template?.icon || '🏥'}</span>
                        <div>
                          <h3 className="text-white font-medium text-lg">{profile.disease_name}</h3>
                          <span className="text-white/50 text-sm">
                            {severityLabels[profile.severity]} · {statusLabels[profile.status]}
                          </span>
                        </div>
                      </div>
                      {profile.tracking_enabled && (
                        <span className="px-2 py-1 bg-green-500/20 text-green-400 text-xs rounded-full">
                          追踪中
                        </span>
                      )}
                    </div>
                    <div className="flex gap-4 text-sm text-white/60">
                      <span>🔥 连续 {profile.current_streak} 天无症状</span>
                      <span>⭐ 最佳 {profile.best_streak} 天</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12">
                <div className="text-6xl mb-4">📋</div>
                <p className="text-white/60 mb-6">暂无疾病档案</p>
                <button
                  onClick={() => setActiveTab('templates')}
                  className="px-6 py-3 bg-purple-600 text-white rounded-xl hover:bg-purple-700 transition-colors"
                >
                  添加疾病档案
                </button>
              </div>
            )}
          </div>
        )}

        {/* 档案详情 */}
        {activeTab === 'profiles' && selectedProfile && (
          <div className="space-y-6">
            <button
              onClick={() => setSelectedProfile(null)}
              className="text-white/70 hover:text-white flex items-center gap-2"
            >
              ← 返回列表
            </button>

            {/* 档案信息 */}
            <div className="bg-white/5 backdrop-blur rounded-xl p-6 border border-white/10">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-4">
                  <span className="text-5xl">{selectedProfile.template?.icon || '🏥'}</span>
                  <div>
                    <h2 className="text-2xl font-bold text-white">{selectedProfile.disease_name}</h2>
                    <p className="text-white/60">
                      {severityLabels[selectedProfile.severity]} · {statusLabels[selectedProfile.status]}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setShowLogModal(true)}
                  className="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-xl font-medium hover:opacity-90 transition-opacity"
                >
                  📝 记录症状
                </button>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div className="bg-white/5 rounded-lg p-4 text-center">
                  <div className="text-3xl font-bold text-green-400">{selectedProfile.current_streak}</div>
                  <div className="text-white/50 text-sm">连续无症状天数</div>
                </div>
                <div className="bg-white/5 rounded-lg p-4 text-center">
                  <div className="text-3xl font-bold text-amber-400">{selectedProfile.best_streak}</div>
                  <div className="text-white/50 text-sm">最佳记录</div>
                </div>
                <div className="bg-white/5 rounded-lg p-4 text-center">
                  <div className="text-3xl font-bold text-white">{stats?.total_logs || 0}</div>
                  <div className="text-white/50 text-sm">总记录数</div>
                </div>
              </div>
            </div>

            {/* 环境预警 */}
            {alert && alert.alert_level !== 'none' && (
              <div className={`rounded-xl p-6 border ${alertColors[alert.alert_level]}`}>
                <h3 className="font-medium mb-4 flex items-center gap-2">
                  <span>⚠️</span> 环境预警
                </h3>
                <div className="grid md:grid-cols-2 gap-4 mb-4">
                  <div className="text-sm opacity-80">
                    <p>天气: {alert.environment.weather} {alert.environment.temperature}°C</p>
                    <p>湿度: {alert.environment.humidity}%</p>
                    <p>空气质量: {alert.environment.aqi_description} (AQI {alert.environment.aqi})</p>
                  </div>
                </div>
                {alert.warnings.length > 0 && (
                  <div className="mb-4">
                    <p className="font-medium mb-2">注意:</p>
                    <ul className="list-disc list-inside space-y-1 text-sm opacity-80">
                      {alert.warnings.map((w, i) => <li key={i}>{w}</li>)}
                    </ul>
                  </div>
                )}
                {alert.recommendations.length > 0 && (
                  <div>
                    <p className="font-medium mb-2">建议:</p>
                    <ul className="list-disc list-inside space-y-1 text-sm opacity-80">
                      {alert.recommendations.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* 统计图表 */}
            {stats && stats.total_logs > 0 && (
              <>
                <div className="bg-white/5 backdrop-blur rounded-xl p-6 border border-white/10">
                  <h3 className="text-white font-medium mb-4">症状统计 (近30天)</h3>
                  <div className="grid md:grid-cols-4 gap-4 mb-6">
                    <div className="bg-white/5 rounded-lg p-4 text-center">
                      <div className="text-2xl font-bold text-white">{stats.avg_severity}</div>
                      <div className="text-white/50 text-sm">平均严重度</div>
                    </div>
                    <div className="bg-white/5 rounded-lg p-4 text-center">
                      <div className="text-2xl font-bold text-green-400">{stats.symptom_free_days}</div>
                      <div className="text-white/50 text-sm">无症状天数</div>
                    </div>
                    <div className="bg-white/5 rounded-lg p-4 text-center">
                      <div className="text-2xl font-bold text-white">{stats.symptom_free_rate}%</div>
                      <div className="text-white/50 text-sm">无症状率</div>
                    </div>
                    <div className="bg-white/5 rounded-lg p-4 text-center">
                      <div className="text-2xl font-bold text-white">{stats.total_logs}</div>
                      <div className="text-white/50 text-sm">记录天数</div>
                    </div>
                  </div>

                  {/* 趋势图 */}
                  {stats.daily_trend.length > 0 && (
                    <div className="mb-6">
                      <h4 className="text-white/70 text-sm mb-3">症状趋势</h4>
                      <div className="flex items-end justify-between h-32 gap-1">
                        {stats.daily_trend.slice(-14).map((day, i) => (
                          <div key={i} className="flex-1 flex flex-col items-center gap-1">
                            <div
                              className={`w-full rounded-t ${
                                day.severity === 0 ? 'bg-green-500' :
                                day.severity <= 3 ? 'bg-yellow-500' :
                                day.severity <= 6 ? 'bg-orange-500' : 'bg-red-500'
                              }`}
                              style={{ height: `${Math.max((day.severity / 10) * 100, 5)}%` }}
                            />
                            <span className="text-white/40 text-xs">
                              {new Date(day.date).getDate()}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 常见症状和触发因素 */}
                  <div className="grid md:grid-cols-2 gap-6">
                    <div>
                      <h4 className="text-white/70 text-sm mb-3">常见症状</h4>
                      <div className="space-y-2">
                        {stats.top_symptoms.map(([symptom, count]) => (
                          <div key={symptom} className="flex items-center justify-between text-sm">
                            <span className="text-white/80">{symptom}</span>
                            <span className="text-white/50">{count}次</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <h4 className="text-white/70 text-sm mb-3">常见触发因素</h4>
                      <div className="space-y-2">
                        {stats.top_triggers.map(([trigger, count]) => (
                          <div key={trigger} className="flex items-center justify-between text-sm">
                            <span className="text-white/80">{trigger}</span>
                            <span className="text-white/50">{count}次</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* 疾病模板 Tab */}
        {activeTab === 'templates' && (
          <div className="space-y-6">
            {templates && templates.length > 0 ? (
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                {templates.map(template => (
                  <div
                    key={template.id}
                    className="bg-white/5 backdrop-blur rounded-xl p-6 border border-white/10 hover:bg-white/10 transition-all"
                  >
                    <div className="flex items-center gap-3 mb-4">
                      <span className="text-4xl">{template.icon}</span>
                      <div>
                        <h3 className="text-white font-medium">{template.display_name}</h3>
                        <span className="text-white/50 text-sm">
                          {categoryLabels[template.category]}
                          {template.environment_sensitive && ' · 环境敏感'}
                        </span>
                      </div>
                    </div>
                    <div className="mb-4">
                      <p className="text-white/60 text-sm mb-2">常见症状:</p>
                      <div className="flex flex-wrap gap-2">
                        {template.symptoms.slice(0, 4).map(s => (
                          <span key={s} className="px-2 py-1 bg-white/10 text-white/70 text-xs rounded">
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                    <button
                      onClick={() => createProfileMutation.mutate({
                        disease_name: template.display_name,
                        template_name: template.name,
                      })}
                      disabled={createProfileMutation.isPending}
                      className="w-full py-2 bg-purple-600/50 hover:bg-purple-600 text-white rounded-lg text-sm transition-colors disabled:opacity-50"
                    >
                      添加到我的档案
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12">
                <div className="text-6xl mb-4">📚</div>
                <p className="text-white/60 mb-6">暂无疾病模板</p>
                <button
                  onClick={() => initMutation.mutate()}
                  disabled={initMutation.isPending}
                  className="px-6 py-3 bg-purple-600 text-white rounded-xl hover:bg-purple-700 transition-colors disabled:opacity-50"
                >
                  {initMutation.isPending ? '初始化中...' : '初始化默认模板'}
                </button>
              </div>
            )}
          </div>
        )}

        {/* 症状记录 Tab */}
        {activeTab === 'log' && (
          <div className="space-y-6">
            {profiles && profiles.length > 0 ? (
              <div className="grid md:grid-cols-2 gap-4">
                {profiles.map(profile => (
                  <div
                    key={profile.id}
                    onClick={() => {
                      setSelectedProfile(profile);
                      setShowLogModal(true);
                    }}
                    className="bg-white/5 backdrop-blur rounded-xl p-6 border border-white/10 hover:bg-white/10 cursor-pointer transition-all"
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-4xl">{profile.template?.icon || '🏥'}</span>
                      <div>
                        <h3 className="text-white font-medium">{profile.disease_name}</h3>
                        <span className="text-white/50 text-sm">点击记录今日症状</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12">
                <p className="text-white/60">请先添加疾病档案</p>
              </div>
            )}
          </div>
        )}
      </main>

      {/* 症状记录弹窗 */}
      {showLogModal && selectedProfile && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-2xl p-6 w-full max-w-lg border border-white/20 max-h-[90vh] overflow-y-auto">
            <h3 className="text-xl font-bold text-white mb-6">
              📝 记录症状 - {selectedProfile.disease_name}
            </h3>

            {/* 严重程度 */}
            <div className="mb-6">
              <label className="block text-white/70 text-sm mb-3">总体严重程度 (0-10)</label>
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min="0"
                  max="10"
                  value={logData.overall_severity}
                  onChange={e => setLogData({ ...logData, overall_severity: Number(e.target.value) })}
                  className="flex-1"
                />
                <span className={`text-2xl font-bold ${
                  logData.overall_severity === 0 ? 'text-green-400' :
                  logData.overall_severity <= 3 ? 'text-yellow-400' :
                  logData.overall_severity <= 6 ? 'text-orange-400' : 'text-red-400'
                }`}>
                  {logData.overall_severity}
                </span>
              </div>
              <p className="text-white/50 text-xs mt-1">0 = 无症状，10 = 非常严重</p>
            </div>

            {/* 备注 */}
            <div className="mb-6">
              <label className="block text-white/70 text-sm mb-2">备注</label>
              <textarea
                value={logData.notes}
                onChange={e => setLogData({ ...logData, notes: e.target.value })}
                placeholder="记录今日状况..."
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/40 focus:outline-none focus:border-purple-500 resize-none"
                rows={3}
              />
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowLogModal(false);
                  setLogData({
                    overall_severity: 0,
                    symptoms: [],
                    triggers: [],
                    treatments: [],
                    notes: '',
                  });
                }}
                className="flex-1 py-3 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-colors"
              >
                取消
              </button>
              <button
                onClick={() => logSymptomsMutation.mutate(logData)}
                disabled={logSymptomsMutation.isPending}
                className="flex-1 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {logSymptomsMutation.isPending ? '提交中...' : '确认记录'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
