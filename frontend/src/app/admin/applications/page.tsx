'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api/client';

interface Application {
  id: number;
  email: string;
  name: string;
  phone: string | null;
  status: 'pending' | 'approved' | 'rejected';
  health_questionnaire: {
    age?: number;
    gender?: string;
    height_cm?: number;
    weight_kg?: number;
    health_goals?: string[];
    chronic_conditions?: string[];
    wearable_devices?: string[];
    exercise_frequency?: string;
    why_join?: string;
  } | null;
  review_note: string | null;
  created_at: string;
  reviewed_at: string | null;
  reviewer_name: string | null;
}

interface InvitationCode {
  id: number;
  code: string;
  note: string | null;
  max_uses: number;
  used_count: number;
  remaining_uses: number;
  is_active: boolean;
  is_valid: boolean;
  expires_at: string | null;
  created_at: string;
  creator_name: string | null;
}

interface Stats {
  invitation_codes: {
    total: number;
    active: number;
    total_uses: number;
  };
  applications: {
    total: number;
    pending: number;
    approved: number;
    rejected: number;
  };
}

export default function AdminApplicationsPage() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const [tab, setTab] = useState<'applications' | 'codes'>('applications');
  const [applications, setApplications] = useState<Application[]>([]);
  const [invitationCodes, setInvitationCodes] = useState<InvitationCode[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedApp, setSelectedApp] = useState<Application | null>(null);
  const [reviewNote, setReviewNote] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('pending');

  // 创建邀请码表单
  const [showCreateCode, setShowCreateCode] = useState(false);
  const [newCodeNote, setNewCodeNote] = useState('');
  const [newCodeMaxUses, setNewCodeMaxUses] = useState(1);
  const [newCodeExpiresDays, setNewCodeExpiresDays] = useState<number | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [appsRes, codesRes, statsRes] = await Promise.all([
        api.get(`/invitation/applications${statusFilter ? `?status=${statusFilter}` : ''}`),
        api.get('/invitation/codes'),
        api.get('/invitation/stats'),
      ]);
      setApplications(appsRes.data);
      setInvitationCodes(codesRes.data);
      setStats(statsRes.data);
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
      return;
    }

    if (user && !user.is_admin) {
      router.push('/');
      return;
    }

    if (user?.is_admin) {
      fetchData();
    }
  }, [authLoading, isAuthenticated, user, router, fetchData]);

  const handleReview = async (approved: boolean) => {
    if (!selectedApp) return;

    try {
      await api.post(`/invitation/applications/${selectedApp.id}/review`, {
        approved,
        note: reviewNote || null,
      });
      setSelectedApp(null);
      setReviewNote('');
      fetchData();
    } catch (error) {
      console.error('Failed to review:', error);
      alert('审批失败，请重试');
    }
  };

  const handleCreateCode = async () => {
    try {
      await api.post('/invitation/codes', {
        note: newCodeNote || null,
        max_uses: newCodeMaxUses,
        expires_days: newCodeExpiresDays,
      });
      setShowCreateCode(false);
      setNewCodeNote('');
      setNewCodeMaxUses(1);
      setNewCodeExpiresDays(null);
      fetchData();
    } catch (error) {
      console.error('Failed to create code:', error);
      alert('创建失败，请重试');
    }
  };

  const handleDisableCode = async (codeId: number) => {
    if (!confirm('确定要禁用此邀请码吗？')) return;

    try {
      await api.delete(`/invitation/codes/${codeId}`);
      fetchData();
    } catch (error) {
      console.error('Failed to disable code:', error);
      alert('操作失败，请重试');
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    alert('已复制到剪贴板');
  };

  if (authLoading || isLoading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="text-purple-400 text-xl">加载中...</div>
      </div>
    );
  }

  if (!user?.is_admin) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900/20 to-slate-900">
      {/* 顶部导航 */}
      <header className="bg-slate-800/50 backdrop-blur-lg border-b border-white/10 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-2xl font-bold text-white flex items-center gap-2">
              <span>🚀</span>
              <span className="hidden sm:inline">Executor Life</span>
            </Link>
            <span className="text-purple-400 text-sm bg-purple-500/20 px-2 py-1 rounded">
              管理后台
            </span>
          </div>
          <Link href="/admin" className="text-gray-400 hover:text-white text-sm">
            ← 返回管理首页
          </Link>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* 统计卡片 */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <div className="bg-slate-800/50 rounded-xl p-4 border border-white/10">
              <div className="text-3xl font-bold text-yellow-400">{stats.applications.pending}</div>
              <div className="text-gray-400 text-sm">待审批申请</div>
            </div>
            <div className="bg-slate-800/50 rounded-xl p-4 border border-white/10">
              <div className="text-3xl font-bold text-green-400">{stats.applications.approved}</div>
              <div className="text-gray-400 text-sm">已通过</div>
            </div>
            <div className="bg-slate-800/50 rounded-xl p-4 border border-white/10">
              <div className="text-3xl font-bold text-purple-400">{stats.invitation_codes.active}</div>
              <div className="text-gray-400 text-sm">有效邀请码</div>
            </div>
            <div className="bg-slate-800/50 rounded-xl p-4 border border-white/10">
              <div className="text-3xl font-bold text-blue-400">{stats.invitation_codes.total_uses}</div>
              <div className="text-gray-400 text-sm">总使用次数</div>
            </div>
          </div>
        )}

        {/* Tab 切换 */}
        <div className="flex gap-4 mb-6">
          <button
            onClick={() => setTab('applications')}
            className={`px-4 py-2 rounded-lg font-medium transition-all ${
              tab === 'applications'
                ? 'bg-purple-500 text-white'
                : 'bg-slate-800/50 text-gray-400 hover:text-white'
            }`}
          >
            📝 用户申请
          </button>
          <button
            onClick={() => setTab('codes')}
            className={`px-4 py-2 rounded-lg font-medium transition-all ${
              tab === 'codes'
                ? 'bg-purple-500 text-white'
                : 'bg-slate-800/50 text-gray-400 hover:text-white'
            }`}
          >
            🎫 邀请码管理
          </button>
        </div>

        {/* 用户申请列表 */}
        {tab === 'applications' && (
          <div className="bg-slate-800/50 rounded-xl border border-white/10 overflow-hidden">
            {/* 筛选 */}
            <div className="p-4 border-b border-white/10 flex items-center gap-4">
              <span className="text-gray-400 text-sm">状态筛选：</span>
              {['pending', 'approved', 'rejected', ''].map((status) => (
                <button
                  key={status || 'all'}
                  onClick={() => {
                    setStatusFilter(status);
                    setIsLoading(true);
                  }}
                  className={`px-3 py-1 rounded text-sm ${
                    statusFilter === status
                      ? 'bg-purple-500 text-white'
                      : 'bg-slate-700 text-gray-300 hover:bg-slate-600'
                  }`}
                >
                  {status === 'pending' ? '待审批' :
                   status === 'approved' ? '已通过' :
                   status === 'rejected' ? '已拒绝' : '全部'}
                </button>
              ))}
            </div>

            {/* 列表 */}
            <div className="divide-y divide-white/10">
              {applications.length === 0 ? (
                <div className="p-8 text-center text-gray-500">
                  暂无申请记录
                </div>
              ) : (
                applications.map((app) => (
                  <div
                    key={app.id}
                    className="p-4 hover:bg-white/5 cursor-pointer transition-all"
                    onClick={() => setSelectedApp(app)}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="flex items-center gap-3">
                          <span className="text-white font-medium">{app.name}</span>
                          <span className={`px-2 py-0.5 rounded text-xs ${
                            app.status === 'pending' ? 'bg-yellow-500/20 text-yellow-400' :
                            app.status === 'approved' ? 'bg-green-500/20 text-green-400' :
                            'bg-red-500/20 text-red-400'
                          }`}>
                            {app.status === 'pending' ? '待审批' :
                             app.status === 'approved' ? '已通过' : '已拒绝'}
                          </span>
                        </div>
                        <div className="text-gray-400 text-sm mt-1">
                          {app.email} · 申请时间：{new Date(app.created_at).toLocaleString('zh-CN')}
                        </div>
                      </div>
                      <span className="text-gray-500">→</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* 邀请码管理 */}
        {tab === 'codes' && (
          <div className="space-y-4">
            {/* 创建邀请码按钮 */}
            <button
              onClick={() => setShowCreateCode(true)}
              className="w-full py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-medium rounded-xl hover:from-purple-700 hover:to-pink-700 transition-all"
            >
              + 生成新邀请码
            </button>

            {/* 邀请码列表 */}
            <div className="bg-slate-800/50 rounded-xl border border-white/10 overflow-hidden">
              <div className="divide-y divide-white/10">
                {invitationCodes.length === 0 ? (
                  <div className="p-8 text-center text-gray-500">
                    暂无邀请码
                  </div>
                ) : (
                  invitationCodes.map((code) => (
                    <div key={code.id} className="p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="flex items-center gap-3">
                            <code className="text-purple-400 font-mono text-lg bg-purple-500/10 px-3 py-1 rounded">
                              {code.code}
                            </code>
                            <button
                              onClick={() => copyToClipboard(code.code)}
                              className="text-gray-500 hover:text-white text-sm"
                            >
                              📋 复制
                            </button>
                            <span className={`px-2 py-0.5 rounded text-xs ${
                              code.is_valid
                                ? 'bg-green-500/20 text-green-400'
                                : 'bg-red-500/20 text-red-400'
                            }`}>
                              {code.is_valid ? '有效' : '已失效'}
                            </span>
                          </div>
                          <div className="text-gray-400 text-sm mt-2">
                            {code.note && <span className="mr-3">📝 {code.note}</span>}
                            <span className="mr-3">已用 {code.used_count}/{code.max_uses} 次</span>
                            {code.expires_at && (
                              <span>过期：{new Date(code.expires_at).toLocaleDateString('zh-CN')}</span>
                            )}
                          </div>
                        </div>
                        {code.is_active && (
                          <button
                            onClick={() => handleDisableCode(code.id)}
                            className="text-red-400 hover:text-red-300 text-sm"
                          >
                            禁用
                          </button>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* 申请详情弹窗 */}
      {selectedApp && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-white/10 flex items-center justify-between">
              <h2 className="text-xl font-bold text-white">申请详情</h2>
              <button
                onClick={() => setSelectedApp(null)}
                className="text-gray-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="p-6 space-y-6">
              {/* 基本信息 */}
              <div>
                <h3 className="text-purple-400 font-medium mb-3">👤 基本信息</h3>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-500">姓名：</span>
                    <span className="text-white ml-2">{selectedApp.name}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">邮箱：</span>
                    <span className="text-white ml-2">{selectedApp.email}</span>
                  </div>
                  {selectedApp.phone && (
                    <div>
                      <span className="text-gray-500">手机：</span>
                      <span className="text-white ml-2">{selectedApp.phone}</span>
                    </div>
                  )}
                  <div>
                    <span className="text-gray-500">申请时间：</span>
                    <span className="text-white ml-2">
                      {new Date(selectedApp.created_at).toLocaleString('zh-CN')}
                    </span>
                  </div>
                </div>
              </div>

              {/* 健康问卷 */}
              {selectedApp.health_questionnaire && (
                <div>
                  <h3 className="text-purple-400 font-medium mb-3">📋 健康画像</h3>
                  <div className="bg-slate-700/50 rounded-lg p-4 space-y-3 text-sm">
                    {selectedApp.health_questionnaire.age && (
                      <div>
                        <span className="text-gray-500">年龄：</span>
                        <span className="text-white ml-2">{selectedApp.health_questionnaire.age} 岁</span>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.gender && (
                      <div>
                        <span className="text-gray-500">性别：</span>
                        <span className="text-white ml-2">
                          {selectedApp.health_questionnaire.gender === 'male' ? '男' : '女'}
                        </span>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.height_cm && selectedApp.health_questionnaire.weight_kg && (
                      <div>
                        <span className="text-gray-500">身高/体重：</span>
                        <span className="text-white ml-2">
                          {selectedApp.health_questionnaire.height_cm}cm / {selectedApp.health_questionnaire.weight_kg}kg
                        </span>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.health_goals?.length ? (
                      <div>
                        <span className="text-gray-500">健康目标：</span>
                        <div className="flex flex-wrap gap-2 mt-1">
                          {selectedApp.health_questionnaire.health_goals.map((goal) => (
                            <span key={goal} className="px-2 py-1 bg-purple-500/20 text-purple-300 rounded text-xs">
                              {goal}
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    {selectedApp.health_questionnaire.chronic_conditions?.length ? (
                      <div>
                        <span className="text-gray-500">慢性病：</span>
                        <div className="flex flex-wrap gap-2 mt-1">
                          {selectedApp.health_questionnaire.chronic_conditions.map((condition) => (
                            <span key={condition} className="px-2 py-1 bg-orange-500/20 text-orange-300 rounded text-xs">
                              {condition}
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    {selectedApp.health_questionnaire.wearable_devices?.length ? (
                      <div>
                        <span className="text-gray-500">穿戴设备：</span>
                        <div className="flex flex-wrap gap-2 mt-1">
                          {selectedApp.health_questionnaire.wearable_devices.map((device) => (
                            <span key={device} className="px-2 py-1 bg-blue-500/20 text-blue-300 rounded text-xs">
                              {device}
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    {selectedApp.health_questionnaire.exercise_frequency && (
                      <div>
                        <span className="text-gray-500">运动频率：</span>
                        <span className="text-white ml-2">{selectedApp.health_questionnaire.exercise_frequency}</span>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.why_join && (
                      <div>
                        <span className="text-gray-500">加入原因：</span>
                        <p className="text-white mt-1 bg-slate-600/50 p-2 rounded">
                          {selectedApp.health_questionnaire.why_join}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* 审批操作 */}
              {selectedApp.status === 'pending' && (
                <div>
                  <h3 className="text-purple-400 font-medium mb-3">✍️ 审批操作</h3>
                  <textarea
                    value={reviewNote}
                    onChange={(e) => setReviewNote(e.target.value)}
                    placeholder="审批备注（选填）"
                    className="w-full p-3 bg-slate-700 border border-white/10 rounded-lg text-white placeholder-gray-500 resize-none mb-4"
                    rows={2}
                  />
                  <div className="flex gap-3">
                    <button
                      onClick={() => handleReview(true)}
                      className="flex-1 py-3 bg-green-600 text-white font-medium rounded-lg hover:bg-green-700 transition-all"
                    >
                      ✓ 通过申请
                    </button>
                    <button
                      onClick={() => handleReview(false)}
                      className="flex-1 py-3 bg-red-600 text-white font-medium rounded-lg hover:bg-red-700 transition-all"
                    >
                      ✗ 拒绝申请
                    </button>
                  </div>
                </div>
              )}

              {/* 已审批信息 */}
              {selectedApp.status !== 'pending' && (
                <div className="bg-slate-700/50 rounded-lg p-4">
                  <div className="text-sm">
                    <span className="text-gray-500">审批结果：</span>
                    <span className={`ml-2 ${
                      selectedApp.status === 'approved' ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {selectedApp.status === 'approved' ? '已通过' : '已拒绝'}
                    </span>
                  </div>
                  {selectedApp.reviewed_at && (
                    <div className="text-sm mt-2">
                      <span className="text-gray-500">审批时间：</span>
                      <span className="text-white ml-2">
                        {new Date(selectedApp.reviewed_at).toLocaleString('zh-CN')}
                      </span>
                    </div>
                  )}
                  {selectedApp.reviewer_name && (
                    <div className="text-sm mt-2">
                      <span className="text-gray-500">审批人：</span>
                      <span className="text-white ml-2">{selectedApp.reviewer_name}</span>
                    </div>
                  )}
                  {selectedApp.review_note && (
                    <div className="text-sm mt-2">
                      <span className="text-gray-500">审批备注：</span>
                      <span className="text-white ml-2">{selectedApp.review_note}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 创建邀请码弹窗 */}
      {showCreateCode && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-2xl max-w-md w-full p-6">
            <h2 className="text-xl font-bold text-white mb-6">生成邀请码</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-purple-200 mb-2">备注（选填）</label>
                <input
                  type="text"
                  value={newCodeNote}
                  onChange={(e) => setNewCodeNote(e.target.value)}
                  placeholder="例：给张三的邀请码"
                  className="w-full p-3 bg-slate-700 border border-white/10 rounded-lg text-white placeholder-gray-500"
                />
              </div>

              <div>
                <label className="block text-sm text-purple-200 mb-2">最大使用次数</label>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={newCodeMaxUses}
                  onChange={(e) => setNewCodeMaxUses(parseInt(e.target.value) || 1)}
                  className="w-full p-3 bg-slate-700 border border-white/10 rounded-lg text-white"
                />
              </div>

              <div>
                <label className="block text-sm text-purple-200 mb-2">有效期（天，留空永不过期）</label>
                <input
                  type="number"
                  min={1}
                  value={newCodeExpiresDays || ''}
                  onChange={(e) => setNewCodeExpiresDays(e.target.value ? parseInt(e.target.value) : null)}
                  placeholder="例：30"
                  className="w-full p-3 bg-slate-700 border border-white/10 rounded-lg text-white placeholder-gray-500"
                />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowCreateCode(false)}
                className="flex-1 py-3 bg-slate-700 text-white font-medium rounded-lg hover:bg-slate-600 transition-all"
              >
                取消
              </button>
              <button
                onClick={handleCreateCode}
                className="flex-1 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-medium rounded-lg hover:from-purple-700 hover:to-pink-700 transition-all"
              >
                生成
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
