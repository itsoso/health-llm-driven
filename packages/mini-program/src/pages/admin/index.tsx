/**
 * 管理员页面
 */
import { useState, useEffect } from 'react';
import { View, Text, Button, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { get, post, put, del } from '../../services/request';
import './index.scss';

interface SystemStats {
  total_users: number;
  active_users: number;
  admin_users: number;
  users_with_garmin: number;
  total_health_records: number;
  total_medical_exams: number;
  total_checkins: number;
  sync_enabled_users: number;
}

interface UserInfo {
  id: number;
  username: string;
  name: string;
  email: string;
  is_active: boolean;
  is_admin: boolean;
  has_garmin: boolean;
  health_records_count: number;
  created_at: string;
}

export default function Admin() {
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [clearingCache, setClearingCache] = useState(false);

  useEffect(() => {
    checkAdmin();
  }, []);

  const checkAdmin = async () => {
    setLoading(true);
    try {
      // 尝试获取管理员统计数据来验证权限
      const statsData = await get<SystemStats>('/admin/stats');
      setStats(statsData);
      setIsAdmin(true);
      loadUsers();
    } catch (error: any) {
      if (error.message?.includes('403') || error.message?.includes('管理员')) {
        setIsAdmin(false);
      }
    } finally {
      setLoading(false);
    }
  };

  const loadUsers = async () => {
    try {
      const usersData = await get<UserInfo[]>('/admin/users');
      setUsers(usersData);
    } catch (error) {
      console.error('加载用户列表失败:', error);
    }
  };

  // 切换用户管理员权限
  const toggleAdmin = async (userId: number, currentIsAdmin: boolean) => {
    Taro.showModal({
      title: '确认操作',
      content: currentIsAdmin ? '确定取消该用户的管理员权限？' : '确定授予该用户管理员权限？',
      success: async (res) => {
        if (res.confirm) {
          try {
            await put(`/admin/users/${userId}/admin`, { is_admin: !currentIsAdmin });
            Taro.showToast({ title: '操作成功', icon: 'success' });
            loadUsers();
          } catch (error) {
            Taro.showToast({ title: '操作失败', icon: 'none' });
          }
        }
      },
    });
  };

  // 切换用户状态
  const toggleActive = async (userId: number, currentIsActive: boolean) => {
    Taro.showModal({
      title: '确认操作',
      content: currentIsActive ? '确定禁用该用户？' : '确定启用该用户？',
      success: async (res) => {
        if (res.confirm) {
          try {
            await put(`/admin/users/${userId}/active`, { is_active: !currentIsActive });
            Taro.showToast({ title: '操作成功', icon: 'success' });
            loadUsers();
          } catch (error) {
            Taro.showToast({ title: '操作失败', icon: 'none' });
          }
        }
      },
    });
  };

  // 触发全局同步
  const handleGlobalSync = async () => {
    Taro.showModal({
      title: '全局同步',
      content: '确定触发所有用户的Garmin数据同步？这可能需要一些时间。',
      success: async (res) => {
        if (res.confirm) {
          setSyncing(true);
          try {
            Taro.showLoading({ title: '同步中...' });
            await post('/admin/garmin/sync-all');
            Taro.hideLoading();
            Taro.showToast({ title: '同步任务已启动', icon: 'success' });
            checkAdmin(); // 刷新统计
          } catch (error) {
            Taro.hideLoading();
            Taro.showToast({ title: '同步失败', icon: 'none' });
          } finally {
            setSyncing(false);
          }
        }
      },
    });
  };

  // 清理无数据缓存
  const handleClearNoDataCache = async () => {
    Taro.showModal({
      title: '清理缓存',
      content: '确定清理所有"无数据"状态的缓存？这将使受影响的用户重新生成AI建议。',
      success: async (res) => {
        if (res.confirm) {
          setClearingCache(true);
          try {
            Taro.showLoading({ title: '清理中...' });
            const result = await del<{ message: string; deleted_count: number }>('/admin/cache/no-data');
            Taro.hideLoading();
            Taro.showToast({ 
              title: `已清理 ${result.deleted_count} 条`, 
              icon: 'success' 
            });
          } catch (error) {
            Taro.hideLoading();
            Taro.showToast({ title: '清理失败', icon: 'none' });
          } finally {
            setClearingCache(false);
          }
        }
      },
    });
  };

  // 清理所有缓存
  const handleClearAllCache = async () => {
    Taro.showModal({
      title: '清理全部缓存',
      content: '⚠️ 确定清理所有用户的缓存？这将强制所有用户重新生成AI建议。',
      success: async (res) => {
        if (res.confirm) {
          setClearingCache(true);
          try {
            Taro.showLoading({ title: '清理中...' });
            const result = await del<{ message: string; deleted_count: number }>('/admin/cache/all');
            Taro.hideLoading();
            Taro.showToast({ 
              title: `已清理 ${result.deleted_count} 条`, 
              icon: 'success' 
            });
          } catch (error) {
            Taro.hideLoading();
            Taro.showToast({ title: '清理失败', icon: 'none' });
          } finally {
            setClearingCache(false);
          }
        }
      },
    });
  };

  // 清理单个用户缓存
  const handleClearUserCache = async (userId: number, userName: string) => {
    Taro.showModal({
      title: '清理用户缓存',
      content: `确定清理用户 ${userName} 的缓存？`,
      success: async (res) => {
        if (res.confirm) {
          try {
            Taro.showLoading({ title: '清理中...' });
            const result = await del<{ message: string; deleted_count: number }>(`/admin/users/${userId}/cache`);
            Taro.hideLoading();
            Taro.showToast({ 
              title: `已清理 ${result.deleted_count} 条`, 
              icon: 'success' 
            });
          } catch (error) {
            Taro.hideLoading();
            Taro.showToast({ title: '清理失败', icon: 'none' });
          }
        }
      },
    });
  };

  if (loading) {
    return (
      <View className="admin-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  if (!isAdmin) {
    return (
      <View className="admin-page no-access">
        <Text className="no-access-icon">🔒</Text>
        <Text className="no-access-title">无访问权限</Text>
        <Text className="no-access-desc">仅管理员可访问此页面</Text>
        <Button 
          className="back-btn"
          onClick={() => Taro.navigateBack()}
        >
          返回
        </Button>
      </View>
    );
  }

  return (
    <ScrollView className="admin-page" scrollY>
      {/* 系统统计 */}
      <View className="section">
        <Text className="section-title">📊 系统统计</Text>
        <View className="stats-grid">
          <View className="stat-card">
            <Text className="stat-value">{stats?.total_users || 0}</Text>
            <Text className="stat-label">总用户</Text>
          </View>
          <View className="stat-card">
            <Text className="stat-value">{stats?.active_users || 0}</Text>
            <Text className="stat-label">活跃用户</Text>
          </View>
          <View className="stat-card">
            <Text className="stat-value">{stats?.admin_users || 0}</Text>
            <Text className="stat-label">管理员</Text>
          </View>
          <View className="stat-card">
            <Text className="stat-value">{stats?.users_with_garmin || 0}</Text>
            <Text className="stat-label">Garmin绑定</Text>
          </View>
          <View className="stat-card">
            <Text className="stat-value">{stats?.total_health_records || 0}</Text>
            <Text className="stat-label">健康记录</Text>
          </View>
          <View className="stat-card">
            <Text className="stat-value">{stats?.total_checkins || 0}</Text>
            <Text className="stat-label">打卡记录</Text>
          </View>
        </View>
      </View>

      {/* 快捷操作 */}
      <View className="section">
        <Text className="section-title">⚡ 快捷操作</Text>
        <View className="action-grid">
          <Button 
            className="action-card"
            onClick={handleGlobalSync}
            loading={syncing}
          >
            <Text className="action-icon">🔄</Text>
            <Text className="action-text">全局同步</Text>
          </Button>
          <Button 
            className="action-card"
            onClick={() => {
              checkAdmin();
              Taro.showToast({ title: '已刷新', icon: 'success' });
            }}
          >
            <Text className="action-icon">📊</Text>
            <Text className="action-text">刷新统计</Text>
          </Button>
          <Button 
            className="action-card warning"
            onClick={handleClearNoDataCache}
            loading={clearingCache}
          >
            <Text className="action-icon">🧹</Text>
            <Text className="action-text">清理无效缓存</Text>
          </Button>
          <Button 
            className="action-card danger"
            onClick={handleClearAllCache}
            loading={clearingCache}
          >
            <Text className="action-icon">🗑️</Text>
            <Text className="action-text">清理全部缓存</Text>
          </Button>
        </View>
      </View>

      {/* 用户管理 */}
      <View className="section">
        <Text className="section-title">👥 用户管理</Text>
        <View className="user-list">
          {users.map(user => (
            <View key={user.id} className="user-card">
              <View className="user-main">
                <View className="user-avatar">
                  {user.is_admin ? '👑' : '👤'}
                </View>
                <View className="user-info">
                  <View className="user-name-row">
                    <Text className="user-name">{user.name || user.username}</Text>
                    {user.is_admin && <Text className="admin-badge">管理员</Text>}
                    {!user.is_active && <Text className="disabled-badge">已禁用</Text>}
                  </View>
                  <Text className="user-email">{user.email || '-'}</Text>
                  <View className="user-stats">
                    <Text className="user-stat">
                      {user.has_garmin ? '⌚' : '○'} Garmin
                    </Text>
                    <Text className="user-stat">
                      📊 {user.health_records_count}条记录
                    </Text>
                  </View>
                </View>
              </View>
              <View className="user-actions">
                <Button 
                  className={`user-action-btn ${user.is_admin ? 'active' : ''}`}
                  onClick={() => toggleAdmin(user.id, user.is_admin)}
                >
                  {user.is_admin ? '取消管理员' : '设为管理员'}
                </Button>
                <Button 
                  className={`user-action-btn ${user.is_active ? 'danger' : 'success'}`}
                  onClick={() => toggleActive(user.id, user.is_active)}
                >
                  {user.is_active ? '禁用' : '启用'}
                </Button>
                <Button 
                  className="user-action-btn warning"
                  onClick={() => handleClearUserCache(user.id, user.name || user.username)}
                >
                  清理缓存
                </Button>
              </View>
            </View>
          ))}
        </View>
      </View>

      <View className="bottom-space" />
    </ScrollView>
  );
}
