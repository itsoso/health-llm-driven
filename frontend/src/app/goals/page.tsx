'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { goalApi } from '@/services/api';
import { format } from 'date-fns';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

function GoalsContent() {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const queryClient = useQueryClient();
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [selectedGoal, setSelectedGoal] = useState<any>(null);
  const [showProgressForm, setShowProgressForm] = useState(false);
  const [progressGoal, setProgressGoal] = useState<any>(null);
  const [progressValue, setProgressValue] = useState('');

  // 获取用户目标
  const { data: goalsData, isLoading } = useQuery({
    queryKey: ['goals', userId],
    queryFn: () => goalApi.getUserGoals(userId!),
    enabled: !!userId,
  });

  const goals = goalsData?.data || [];

  // 创建目标
  const createMutation = useMutation({
    mutationFn: (data: any) => goalApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals', userId] });
      setShowCreateForm(false);
    },
  });

  // 更新进度
  const updateProgressMutation = useMutation({
    mutationFn: ({ goalId, progressDate, progressValue }: { goalId: number; progressDate: string; progressValue: number }) =>
      goalApi.updateProgress(goalId, progressDate, progressValue),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals', userId] });
      setShowProgressForm(false);
      setProgressGoal(null);
      setProgressValue('');
      // 如果有选中的目标，也更新它
      if (selectedGoal && progressGoal && selectedGoal.id === progressGoal.id) {
        setSelectedGoal(null);
      }
    },
  });

  // 从分析生成目标
  const generateMutation = useMutation({
    mutationFn: () => goalApi.generateFromAnalysis(userId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals', userId] });
    },
  });

  const [formData, setFormData] = useState({
    user_id: userId,
    goal_type: 'exercise',
    goal_period: 'daily',
    title: '',
    description: '',
    target_value: '',
    target_unit: '',
    start_date: new Date().toISOString().split('T')[0],
    end_date: '',
    implementation_steps: '',
    priority: 5,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate({
      ...formData,
      target_value: parseFloat(formData.target_value) || 0,
      priority: parseInt(formData.priority as any) || 5,
    });
  };

  const handleProgressSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (progressGoal && progressValue) {
      updateProgressMutation.mutate({
        goalId: progressGoal.id,
        progressDate: format(new Date(), 'yyyy-MM-dd'),
        progressValue: parseFloat(progressValue),
      });
    }
  };

  const openProgressForm = (goal: any, e?: React.MouseEvent) => {
    if (e) {
      e.stopPropagation();
    }
    setProgressGoal(goal);
    setProgressValue(goal.current_value?.toString() || '');
    setShowProgressForm(true);
  };

  const getTypeIcon = (type: string) => {
    const icons: Record<string, string> = {
      diet: '🥗',
      exercise: '🏃',
      sleep: '😴',
      water: '💧',
      supplement: '💊',
      outdoor: '🌳',
      weight: '⚖️',
      other: '📌',
    };
    return icons[type] || '📌';
  };

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      active: 'bg-green-100 text-green-800',
      completed: 'bg-blue-100 text-blue-800',
      paused: 'bg-yellow-100 text-yellow-800',
      cancelled: 'bg-gray-100 text-gray-800',
    };
    return colors[status] || colors.active;
  };

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      active: '进行中',
      completed: '已完成',
      paused: '已暂停',
      cancelled: '已取消',
    };
    return labels[status] || status;
  };

  if (isLoading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
        <div className="max-w-6xl mx-auto">
          <div className="text-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
            <p className="text-gray-800 text-lg font-medium">加载中...</p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
      <div className="max-w-6xl mx-auto">
        {/* 头部操作栏 */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <p className="text-gray-600 text-sm">管理你的健康目标</p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => generateMutation.mutate()}
              disabled={generateMutation.isPending}
              className="px-4 py-2 bg-purple-600 text-white font-semibold rounded-lg hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2 shadow-md transition-all"
            >
              {generateMutation.isPending && (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
              )}
              <span>🤖</span>
              AI 生成目标
            </button>
            <button
              onClick={() => setShowCreateForm(!showCreateForm)}
              className="px-4 py-2 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold rounded-lg hover:from-indigo-700 hover:to-purple-700 shadow-md transition-all"
            >
              {showCreateForm ? '取消' : '+ 新建目标'}
            </button>
          </div>
        </div>

        {/* 创建目标表单 */}
        {showCreateForm && (
          <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-indigo-200">
            <h3 className="text-xl font-bold text-gray-900 mb-4">创建新目标</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    目标类型
                  </label>
                  <select
                    value={formData.goal_type}
                    onChange={(e) => setFormData({ ...formData, goal_type: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 text-gray-900"
                  >
                    <option value="exercise">锻炼</option>
                    <option value="diet">饮食</option>
                    <option value="sleep">睡眠</option>
                    <option value="water">饮水</option>
                    <option value="supplement">补剂</option>
                    <option value="outdoor">户外活动</option>
                    <option value="weight">体重</option>
                    <option value="other">其他</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    目标周期
                  </label>
                  <select
                    value={formData.goal_period}
                    onChange={(e) => setFormData({ ...formData, goal_period: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 text-gray-900"
                  >
                    <option value="daily">每日</option>
                    <option value="weekly">每周</option>
                    <option value="monthly">每月</option>
                    <option value="yearly">每年</option>
                  </select>
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    目标标题 *
                  </label>
                  <input
                    type="text"
                    required
                    value={formData.title}
                    onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 text-gray-900"
                    placeholder="例如：每日运动30分钟"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    目标描述
                  </label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 text-gray-900"
                    rows={2}
                    placeholder="描述你的目标..."
                  />
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    目标值
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={formData.target_value}
                    onChange={(e) => setFormData({ ...formData, target_value: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 text-gray-900"
                  />
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    单位
                  </label>
                  <input
                    type="text"
                    value={formData.target_unit}
                    onChange={(e) => setFormData({ ...formData, target_unit: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 text-gray-900"
                    placeholder="例如：分钟、步、杯"
                  />
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    开始日期 *
                  </label>
                  <input
                    type="date"
                    required
                    value={formData.start_date}
                    onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 text-gray-900"
                  />
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    结束日期（可选）
                  </label>
                  <input
                    type="date"
                    value={formData.end_date}
                    onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 text-gray-900"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    实现步骤
                  </label>
                  <textarea
                    value={formData.implementation_steps}
                    onChange={(e) => setFormData({ ...formData, implementation_steps: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 text-gray-900"
                    rows={3}
                    placeholder="每行一个步骤..."
                  />
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    优先级 (1-10)
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="10"
                    value={formData.priority}
                    onChange={(e) => setFormData({ ...formData, priority: parseInt(e.target.value) || 5 })}
                    className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 text-gray-900"
                  />
                </div>
              </div>

              <div className="flex gap-3 pt-4">
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="flex-1 bg-gradient-to-r from-indigo-600 to-purple-600 text-white py-3 rounded-lg font-semibold hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 shadow-md transition-all"
                >
                  {createMutation.isPending ? '创建中...' : '创建目标'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowCreateForm(false)}
                  className="px-6 py-3 bg-gray-200 text-gray-800 rounded-lg font-semibold hover:bg-gray-300 transition-all"
                >
                  取消
                </button>
              </div>
            </form>
          </div>
        )}

        {/* 目标列表 */}
        {goals.length === 0 ? (
          <div className="text-center py-20 bg-white rounded-xl shadow-md">
            <div className="text-6xl mb-4">🎯</div>
            <h3 className="text-2xl font-bold text-gray-800 mb-2">还没有目标</h3>
            <p className="text-gray-600 mb-6">创建你的第一个健康目标，开始你的健康旅程</p>
            <button
              onClick={() => setShowCreateForm(true)}
              className="px-6 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold rounded-lg hover:from-indigo-700 hover:to-purple-700 shadow-md transition-all"
            >
              创建目标
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {goals.map((goal: any) => (
              <div
                key={goal.id}
                className="bg-white rounded-xl shadow-md hover:shadow-lg transition-all p-6 border border-gray-200"
              >
                <div 
                  className="cursor-pointer"
                  onClick={() => setSelectedGoal(goal)}
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <span className="text-3xl">{getTypeIcon(goal.goal_type)}</span>
                      <div>
                        <h3 className="text-lg font-bold text-gray-900">{goal.title}</h3>
                        <span className={`text-xs px-2 py-1 rounded-full font-semibold ${getStatusColor(goal.status)}`}>
                          {getStatusLabel(goal.status)}
                        </span>
                      </div>
                    </div>
                  </div>

                  {goal.description && (
                    <p className="text-sm text-gray-600 mb-4 line-clamp-2">{goal.description}</p>
                  )}

                  <div className="space-y-2">
                    {goal.target_value && (
                      <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-600">目标值:</span>
                        <span className="text-sm font-bold text-gray-900">
                          {goal.target_value} {goal.target_unit}
                        </span>
                      </div>
                    )}

                    {goal.current_value !== undefined && (
                      <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-600">当前值:</span>
                        <span className="text-sm font-bold text-indigo-600">
                          {goal.current_value} {goal.target_unit}
                        </span>
                      </div>
                    )}

                    {goal.target_value > 0 && (
                      <div className="mt-3">
                        <div className="flex justify-between text-xs text-gray-600 mb-1">
                          <span>进度</span>
                          <span>{Math.round(((goal.current_value || 0) / goal.target_value) * 100)}%</span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2">
                          <div
                            className="bg-gradient-to-r from-indigo-600 to-purple-600 h-2 rounded-full transition-all"
                            style={{ width: `${Math.min(((goal.current_value || 0) / goal.target_value) * 100, 100)}%` }}
                          ></div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* 更新进度按钮 */}
                <div className="mt-4 pt-4 border-t border-gray-200">
                  <div className="flex items-center justify-between">
                    <div className="text-xs text-gray-500">
                      <span>🔥 优先级: {goal.priority}</span>
                      <span className="ml-3">📅 {goal.goal_period === 'daily' ? '每日' : goal.goal_period === 'weekly' ? '每周' : goal.goal_period === 'monthly' ? '每月' : '每年'}</span>
                    </div>
                    <button
                      onClick={(e) => openProgressForm(goal, e)}
                      className="px-3 py-1.5 bg-indigo-100 text-indigo-700 text-sm font-semibold rounded-lg hover:bg-indigo-200 transition-all"
                    >
                      📝 更新进度
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 进度更新弹窗 */}
        {showProgressForm && progressGoal && (
          <div
            className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
            onClick={() => {
              setShowProgressForm(false);
              setProgressGoal(null);
            }}
          >
            <div
              className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <span className="text-3xl">{getTypeIcon(progressGoal.goal_type)}</span>
                  <div>
                    <h3 className="text-xl font-bold text-gray-900">更新进度</h3>
                    <p className="text-sm text-gray-600">{progressGoal.title}</p>
                  </div>
                </div>
                <button
                  onClick={() => {
                    setShowProgressForm(false);
                    setProgressGoal(null);
                  }}
                  className="text-gray-500 hover:text-gray-700 text-2xl"
                >
                  ×
                </button>
              </div>

              <form onSubmit={handleProgressSubmit} className="space-y-4">
                <div className="bg-gray-50 rounded-lg p-4 mb-4">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm text-gray-600">目标值</span>
                    <span className="text-lg font-bold text-gray-900">{progressGoal.target_value} {progressGoal.target_unit}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">当前进度</span>
                    <span className="text-lg font-bold text-indigo-600">
                      {Math.round(((progressGoal.current_value || 0) / progressGoal.target_value) * 100)}%
                    </span>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-800 mb-2">
                    新的当前值 ({progressGoal.target_unit})
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    required
                    value={progressValue}
                    onChange={(e) => setProgressValue(e.target.value)}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 text-gray-900 text-lg"
                    placeholder={`输入当前${progressGoal.target_unit || '数值'}`}
                  />
                </div>

                {/* 快捷按钮 */}
                {progressGoal.goal_type === 'weight' && (
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setProgressValue((parseFloat(progressValue) - 0.5).toString())}
                      className="flex-1 py-2 bg-green-100 text-green-700 rounded-lg font-medium hover:bg-green-200"
                    >
                      -0.5
                    </button>
                    <button
                      type="button"
                      onClick={() => setProgressValue((parseFloat(progressValue) - 0.1).toString())}
                      className="flex-1 py-2 bg-green-100 text-green-700 rounded-lg font-medium hover:bg-green-200"
                    >
                      -0.1
                    </button>
                    <button
                      type="button"
                      onClick={() => setProgressValue((parseFloat(progressValue) + 0.1).toString())}
                      className="flex-1 py-2 bg-red-100 text-red-700 rounded-lg font-medium hover:bg-red-200"
                    >
                      +0.1
                    </button>
                    <button
                      type="button"
                      onClick={() => setProgressValue((parseFloat(progressValue) + 0.5).toString())}
                      className="flex-1 py-2 bg-red-100 text-red-700 rounded-lg font-medium hover:bg-red-200"
                    >
                      +0.5
                    </button>
                  </div>
                )}

                <div className="text-sm text-gray-500">
                  📅 更新日期: {format(new Date(), 'yyyy-MM-dd')}
                </div>

                <div className="flex gap-3 pt-2">
                  <button
                    type="submit"
                    disabled={updateProgressMutation.isPending || !progressValue}
                    className="flex-1 bg-gradient-to-r from-indigo-600 to-purple-600 text-white py-3 rounded-lg font-semibold hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 shadow-md transition-all"
                  >
                    {updateProgressMutation.isPending ? '更新中...' : '✓ 确认更新'}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setShowProgressForm(false);
                      setProgressGoal(null);
                    }}
                    className="px-6 py-3 bg-gray-200 text-gray-800 rounded-lg font-semibold hover:bg-gray-300 transition-all"
                  >
                    取消
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* 目标详情弹窗 */}
        {selectedGoal && (
          <div
            className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
            onClick={() => setSelectedGoal(null)}
          >
            <div
              className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start justify-between mb-6">
                <div className="flex items-center gap-3">
                  <span className="text-4xl">{getTypeIcon(selectedGoal.goal_type)}</span>
                  <div>
                    <h2 className="text-2xl font-bold text-gray-900">{selectedGoal.title}</h2>
                    <span className={`text-xs px-2 py-1 rounded-full font-semibold ${getStatusColor(selectedGoal.status)}`}>
                      {getStatusLabel(selectedGoal.status)}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedGoal(null)}
                  className="text-gray-500 hover:text-gray-700 text-2xl"
                >
                  ×
                </button>
              </div>

              {selectedGoal.description && (
                <div className="mb-6">
                  <h3 className="text-sm font-bold text-gray-700 mb-2">描述</h3>
                  <p className="text-gray-800">{selectedGoal.description}</p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4 mb-6">
                <div className="p-4 bg-indigo-50 rounded-lg">
                  <div className="text-sm text-gray-600 mb-1">目标值</div>
                  <div className="text-2xl font-bold text-indigo-600">
                    {selectedGoal.target_value} {selectedGoal.target_unit}
                  </div>
                </div>
                <div className="p-4 bg-purple-50 rounded-lg">
                  <div className="text-sm text-gray-600 mb-1">当前值</div>
                  <div className="text-2xl font-bold text-purple-600">
                    {selectedGoal.current_value || 0} {selectedGoal.target_unit}
                  </div>
                </div>
              </div>

              {/* 进度条 */}
              {selectedGoal.target_value > 0 && (
                <div className="mb-6">
                  <div className="flex justify-between text-sm text-gray-600 mb-2">
                    <span>完成进度</span>
                    <span className="font-bold">{Math.round(((selectedGoal.current_value || 0) / selectedGoal.target_value) * 100)}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-4">
                    <div
                      className="bg-gradient-to-r from-indigo-600 to-purple-600 h-4 rounded-full transition-all"
                      style={{ width: `${Math.min(((selectedGoal.current_value || 0) / selectedGoal.target_value) * 100, 100)}%` }}
                    ></div>
                  </div>
                </div>
              )}

              {/* 更新进度按钮 */}
              <button
                onClick={() => openProgressForm(selectedGoal)}
                className="w-full mb-6 py-3 bg-gradient-to-r from-green-500 to-teal-600 text-white font-semibold rounded-lg hover:from-green-600 hover:to-teal-700 shadow-md transition-all flex items-center justify-center gap-2"
              >
                📝 更新进度
              </button>

              {selectedGoal.implementation_steps && (
                <div className="mb-6">
                  <h3 className="text-sm font-bold text-gray-700 mb-2">实现步骤</h3>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <pre className="text-sm text-gray-800 whitespace-pre-wrap font-sans">
                      {selectedGoal.implementation_steps}
                    </pre>
                  </div>
                </div>
              )}

              <div className="border-t pt-4">
                <div className="grid grid-cols-2 gap-4 text-sm text-gray-600">
                  <div>
                    <span className="font-semibold">开始日期:</span> {selectedGoal.start_date}
                  </div>
                  {selectedGoal.end_date && (
                    <div>
                      <span className="font-semibold">结束日期:</span> {selectedGoal.end_date}
                    </div>
                  )}
                  <div>
                    <span className="font-semibold">优先级:</span> {selectedGoal.priority}/10
                  </div>
                  <div>
                    <span className="font-semibold">周期:</span>{' '}
                    {selectedGoal.goal_period === 'daily' ? '每日' : selectedGoal.goal_period === 'weekly' ? '每周' : selectedGoal.goal_period === 'monthly' ? '每月' : '每年'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

// 导出受保护的页面
export default function GoalsPage() {
  return (
    <ProtectedRoute>
      <GoalsContent />
    </ProtectedRoute>
  );
}
