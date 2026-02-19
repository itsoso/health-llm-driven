/**
 * 调度器配置页面
 * 查看定时任务状态、手动触发
 */
import { useState, useEffect } from 'react';
import { View, Text } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { llmAPI } from '../../services/llmApi';
import type { SchedulerTask } from '../../types/llm';
import './index.scss';

export default function LLMScheduler() {
  const [tasks, setTasks] = useState<SchedulerTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState<string | null>(null);

  useEffect(() => {
    loadTasks();
  }, []);

  const loadTasks = async () => {
    try {
      setLoading(true);
      const res = await llmAPI.getSchedulerTasks();
      if (res.ok && res.tasks) {
        setTasks(res.tasks);
      }
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  const handleTrigger = async (taskId: string) => {
    const confirm = await Taro.showModal({
      title: '确认',
      content: '确定要手动触发此任务吗？',
    });
    if (!confirm.confirm) return;

    try {
      setTriggering(taskId);
      const res = await llmAPI.triggerTask(taskId);
      if (res.ok) {
        Taro.showToast({ title: '已触发', icon: 'success' });
        setTimeout(() => loadTasks(), 2000);
      }
    } catch (error: any) {
      Taro.showToast({ title: error?.message || '触发失败', icon: 'none' });
    } finally {
      setTriggering(null);
    }
  };

  const formatTime = (timeStr?: string) => {
    if (!timeStr) return '-';
    const d = new Date(timeStr);
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  };

  const getStatusIcon = (task: SchedulerTask) => {
    if (!task.enabled) return '⏸️';
    if (task.last_status === 'success') return '✅';
    if (task.last_status === 'failed') return '❌';
    return '⏳';
  };

  return (
    <View className="scheduler-page">
      {/* 标题 */}
      <View className="page-header">
        <Text className="page-title">定时任务</Text>
        <Text className="page-subtitle">管理自动化分析任务</Text>
      </View>

      {loading ? (
        <View className="loading-tip">
          <Text>加载中...</Text>
        </View>
      ) : tasks.length === 0 ? (
        <View className="empty-tip">
          <Text>暂无定时任务</Text>
        </View>
      ) : (
        <View className="task-list">
          {tasks.map((task) => (
            <View key={task.id} className="task-card">
              <View className="task-header">
                <Text className="task-icon">{getStatusIcon(task)}</Text>
                <View className="task-info">
                  <Text className="task-name">{task.name}</Text>
                  <Text className="task-cron">{task.cron}</Text>
                </View>
                <View
                  className={`trigger-btn ${triggering === task.id ? 'disabled' : ''}`}
                  onClick={() => triggering !== task.id && handleTrigger(task.id)}
                >
                  <Text>{triggering === task.id ? '...' : '触发'}</Text>
                </View>
              </View>

              <View className="task-stats">
                <View className="stat-item">
                  <Text className="stat-label">类型</Text>
                  <Text className="stat-value">{task.type}</Text>
                </View>
                <View className="stat-item">
                  <Text className="stat-label">运行次数</Text>
                  <Text className="stat-value">{task.run_count}</Text>
                </View>
                <View className="stat-item">
                  <Text className="stat-label">成功</Text>
                  <Text className="stat-value success">{task.success_count}</Text>
                </View>
                <View className="stat-item">
                  <Text className="stat-label">失败</Text>
                  <Text className="stat-value fail">{task.fail_count}</Text>
                </View>
              </View>

              <View className="task-meta">
                <Text className="meta-text">
                  上次运行: {formatTime(task.last_run_at)}
                </Text>
                <Text className={`task-status ${task.enabled ? 'enabled' : 'disabled'}`}>
                  {task.enabled ? '已启用' : '已停用'}
                </Text>
              </View>

              {task.last_error && (
                <View className="task-error">
                  <Text className="error-text">{task.last_error}</Text>
                </View>
              )}
            </View>
          ))}
        </View>
      )}

      {/* 刷新按钮 */}
      <View className="refresh-section">
        <View className="refresh-btn" onClick={loadTasks}>
          <Text>刷新</Text>
        </View>
      </View>
    </View>
  );
}
