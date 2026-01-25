/**
 * 管理员页面 - 包含邀请码管理
 */
import { useState, useEffect } from 'react';
import { View, Text, Button, ScrollView, Input } from '@tarojs/components';
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

interface InvitationStats {
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

interface UserApplication {
  id: number;
  email: string;
  name: string;
  phone: string | null;
  status: string;
  review_note: string | null;
  created_at: string;
  reviewed_at: string | null;
  reviewer_name: string | null;
}

type TabType = 'overview' | 'invitation' | 'users';

export default function Admin() {
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  
  // 系统统计
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [clearingCache, setClearingCache] = useState(false);
  
  // 邀请码相关
  const [invitationStats, setInvitationStats] = useState<InvitationStats | null>(null);
  const [invitationCodes, setInvitationCodes] = useState<InvitationCode[]>([]);
  const [applications, setApplications] = useState<UserApplication[]>([]);
  const [showCreateCode, setShowCreateCode] = useState(false);
  const [newCodeNote, setNewCodeNote] = useState('');
  const [newCodeMaxUses, setNewCodeMaxUses] = useState('10');
  const [creatingCode, setCreatingCode] = useState(false);

  useEffect(() => {
    checkAdmin();
  }, []);

  const checkAdmin = async () => {
    setLoading(true);
    try {
      const statsData = await get<SystemStats>('/admin/stats');
      setStats(statsData);
      setIsAdmin(true);
      loadAllData();
    } catch (error: any) {
      if (error.message?.includes('403') || error.message?.includes('管理员')) {
        setIsAdmin(false);
      }
    } finally {
      setLoading(false);
    }
  };

  const loadAllData = async () => {
    await Promise.all([
      loadUsers(),
      loadInvitationStats(),
      loadInvitationCodes(),
      loadApplications()
    ]);
  };

  const loadUsers = async () => {
    try {
      const usersData = await get<UserInfo[]>('/admin/users');
      setUsers(usersData);
    } catch (error) {
      console.error('加载用户列表失败:', error);
    }
  };

  const loadInvitationStats = async () => {
    try {
      const data = await get<InvitationStats>('/invitation/stats');
      setInvitationStats(data);
    } catch (error) {
      console.error('加载邀请统计失败:', error);
    }
  };

  const loadInvitationCodes = async () => {
    try {
      const data = await get<InvitationCode[]>('/invitation/codes');
      setInvitationCodes(data);
    } catch (error) {
      console.error('加载邀请码失败:', error);
    }
  };

  const loadApplications = async () => {
    try {
      const data = await get<UserApplication[]>('/invitation/applications');
      setApplications(data);
    } catch (error) {
      console.error('加载申请列表失败:', error);
    }
  };

  // 创建邀请码
  const handleCreateCode = async () => {
    if (creatingCode) return;
    
    setCreatingCode(true);
    try {
      const result = await post<InvitationCode>('/invitation/codes', {
        note: newCodeNote || null,
        max_uses: parseInt(newCodeMaxUses) || 10,
        expires_days: null
      });
      
      Taro.showModal({
        title: '邀请码创建成功',
        content: `邀请码: ${result.code}\n可使用次数: ${result.max_uses}`,
        showCancel: true,
        cancelText: '关闭',
        confirmText: '复制',
        success: (res) => {
          if (res.confirm) {
            Taro.setClipboardData({ data: result.code });
          }
        }
      });
      
      setShowCreateCode(false);
      setNewCodeNote('');
      setNewCodeMaxUses('10');
      loadInvitationCodes();
      loadInvitationStats();
    } catch (error) {
      Taro.showToast({ title: '创建失败', icon: 'none' });
    } finally {
      setCreatingCode(false);
    }
  };

  // 禁用邀请码
  const handleDisableCode = async (codeId: number, code: string) => {
    Taro.showModal({
      title: '确认禁用',
      content: `确定禁用邀请码 ${code}？`,
      success: async (res) => {
        if (res.confirm) {
          try {
            await del(`/invitation/codes/${codeId}`);
            Taro.showToast({ title: '已禁用', icon: 'success' });
            loadInvitationCodes();
            loadInvitationStats();
          } catch (error) {
            Taro.showToast({ title: '操作失败', icon: 'none' });
          }
        }
      }
    });
  };

  // 复制邀请码
  const handleCopyCode = (code: string) => {
    Taro.setClipboardData({
      data: code,
      success: () => {
        Taro.showToast({ title: '已复制', icon: 'success' });
      }
    });
  };

  // 审批申请
  const handleReviewApplication = async (appId: number, approved: boolean, name: string) => {
    const action = approved ? '通过' : '拒绝';
    Taro.showModal({
      title: `确认${action}`,
      content: `确定${action}用户 ${name} 的申请？`,
      success: async (res) => {
        if (res.confirm) {
          try {
            await post(`/invitation/applications/${appId}/review`, {
              approved,
              note: approved ? '审核通过' : '审核未通过'
            });
            Taro.showToast({ title: `已${action}`, icon: 'success' });
            loadApplications();
            loadInvitationStats();
          } catch (error) {
            Taro.showToast({ title: '操作失败', icon: 'none' });
          }
        }
      }
    });
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
      content: '确定触发所有用户的Garmin数据同步？',
      success: async (res) => {
        if (res.confirm) {
          setSyncing(true);
          try {
            Taro.showLoading({ title: '同步中...' });
            await post('/admin/garmin/sync-all');
            Taro.hideLoading();
            Taro.showToast({ title: '同步任务已启动', icon: 'success' });
            checkAdmin();
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

  // 清理缓存
  const handleClearCache = async (type: 'no-data' | 'all') => {
    const title = type === 'all' ? '清理全部缓存' : '清理无效缓存';
    const content = type === 'all' 
      ? '⚠️ 确定清理所有用户的缓存？' 
      : '确定清理所有"无数据"状态的缓存？';
    
    Taro.showModal({
      title,
      content,
      success: async (res) => {
        if (res.confirm) {
          setClearingCache(true);
          try {
            Taro.showLoading({ title: '清理中...' });
            const endpoint = type === 'all' ? '/admin/cache/all' : '/admin/cache/no-data';
            const result = await del<{ deleted_count: number }>(endpoint);
            Taro.hideLoading();
            Taro.showToast({ title: `已清理 ${result.deleted_count} 条`, icon: 'success' });
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
        <Button className="back-btn" onClick={() => Taro.navigateBack()}>返回</Button>
      </View>
    );
  }

  const pendingCount = applications.filter(a => a.status === 'pending').length;

  return (
    <ScrollView className="admin-page" scrollY>
      {/* Tab 切换 */}
      <View className="tab-bar">
        <View 
          className={`tab-item ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <Text>📈 概览</Text>
        </View>
        <View 
          className={`tab-item ${activeTab === 'invitation' ? 'active' : ''}`}
          onClick={() => setActiveTab('invitation')}
        >
          <Text>🎫 邀请码</Text>
          {pendingCount > 0 && <View className="badge">{pendingCount}</View>}
        </View>
        <View 
          className={`tab-item ${activeTab === 'users' ? 'active' : ''}`}
          onClick={() => setActiveTab('users')}
        >
          <Text>👥 用户</Text>
        </View>
      </View>

      {/* 概览 Tab */}
      {activeTab === 'overview' && (
        <>
      {/* 系统统计 */}
      <View className="section">
        <Text className="section-title">📈 系统统计</Text>
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
            <Text className="stat-value">{stats?.users_with_garmin || 0}</Text>
            <Text className="stat-label">Garmin绑定</Text>
          </View>
              <View className="stat-card highlight">
                <Text className="stat-value">{invitationStats?.applications.pending || 0}</Text>
                <Text className="stat-label">待审批</Text>
              </View>
          <View className="stat-card">
                <Text className="stat-value">{invitationStats?.invitation_codes.active || 0}</Text>
                <Text className="stat-label">有效邀请码</Text>
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
              <Button className="action-card" onClick={handleGlobalSync} loading={syncing}>
            <Text className="action-icon">🔄</Text>
            <Text className="action-text">全局同步</Text>
          </Button>
              <Button className="action-card" onClick={() => { checkAdmin(); loadAllData(); }}>
            <Text className="action-icon">🔄</Text>
                <Text className="action-text">刷新数据</Text>
          </Button>
              <Button className="action-card warning" onClick={() => handleClearCache('no-data')} loading={clearingCache}>
            <Text className="action-icon">🧹</Text>
            <Text className="action-text">清理无效缓存</Text>
          </Button>
              <Button className="action-card danger" onClick={() => handleClearCache('all')} loading={clearingCache}>
            <Text className="action-icon">🗑️</Text>
            <Text className="action-text">清理全部缓存</Text>
          </Button>
        </View>
          </View>
        </>
      )}

      {/* 邀请码 Tab */}
      {activeTab === 'invitation' && (
        <>
          {/* 邀请码统计 */}
          <View className="section">
            <Text className="section-title">📈 邀请统计</Text>
            <View className="stats-grid small">
              <View className="stat-card">
                <Text className="stat-value">{invitationStats?.invitation_codes.total || 0}</Text>
                <Text className="stat-label">总邀请码</Text>
              </View>
              <View className="stat-card">
                <Text className="stat-value">{invitationStats?.invitation_codes.active || 0}</Text>
                <Text className="stat-label">有效</Text>
              </View>
              <View className="stat-card">
                <Text className="stat-value">{invitationStats?.invitation_codes.total_uses || 0}</Text>
                <Text className="stat-label">已使用</Text>
              </View>
              <View className="stat-card highlight">
                <Text className="stat-value">{invitationStats?.applications.pending || 0}</Text>
                <Text className="stat-label">待审批</Text>
              </View>
            </View>
          </View>

          {/* 创建邀请码 */}
          <View className="section">
            <View className="section-header-row">
              <Text className="section-title">🎫 邀请码管理</Text>
              <Button 
                className="create-btn"
                onClick={() => setShowCreateCode(!showCreateCode)}
              >
                {showCreateCode ? '取消' : '+ 创建'}
              </Button>
      </View>

            {showCreateCode && (
              <View className="create-form">
                <View className="form-row">
                  <Text className="form-label">备注</Text>
                  <Input 
                    className="form-input"
                    placeholder="如：给XXX使用"
                    value={newCodeNote}
                    onInput={(e) => setNewCodeNote(e.detail.value)}
                  />
                </View>
                <View className="form-row">
                  <Text className="form-label">可用次数</Text>
                  <Input 
                    className="form-input short"
                    type="number"
                    placeholder="10"
                    value={newCodeMaxUses}
                    onInput={(e) => setNewCodeMaxUses(e.detail.value)}
                  />
                </View>
                <Button 
                  className="submit-btn"
                  onClick={handleCreateCode}
                  loading={creatingCode}
                >
                  生成邀请码
                </Button>
              </View>
            )}

            {/* 邀请码列表 */}
            <View className="code-list">
              {invitationCodes.map(code => (
                <View key={code.id} className={`code-card ${!code.is_valid ? 'disabled' : ''}`}>
                  <View className="code-main">
                    <View className="code-value" onClick={() => handleCopyCode(code.code)}>
                      <Text className="code-text">{code.code}</Text>
                      <Text className="copy-hint">点击复制</Text>
                    </View>
                    <View className="code-info">
                      <Text className="code-usage">
                        已用 {code.used_count}/{code.max_uses}
                      </Text>
                      {code.note && <Text className="code-note">{code.note}</Text>}
                    </View>
                  </View>
                  {code.is_active && code.is_valid && (
                    <Button 
                      className="disable-btn"
                      onClick={() => handleDisableCode(code.id, code.code)}
                    >
                      禁用
                    </Button>
                  )}
                  {!code.is_valid && (
                    <Text className="invalid-tag">
                      {!code.is_active ? '已禁用' : '已用完'}
                    </Text>
                  )}
                </View>
              ))}
            </View>
          </View>

          {/* 待审批申请 */}
          {applications.filter(a => a.status === 'pending').length > 0 && (
            <View className="section">
              <Text className="section-title">⏳ 待审批申请</Text>
              <View className="application-list">
                {applications.filter(a => a.status === 'pending').map(app => (
                  <View key={app.id} className="application-card">
                    <View className="app-info">
                      <Text className="app-name">{app.name}</Text>
                      <Text className="app-email">{app.email}</Text>
                      <Text className="app-time">
                        申请时间: {new Date(app.created_at).toLocaleString('zh-CN')}
                      </Text>
                    </View>
                    <View className="app-actions">
                      <Button 
                        className="approve-btn"
                        onClick={() => handleReviewApplication(app.id, true, app.name)}
                      >
                        通过
                      </Button>
                      <Button 
                        className="reject-btn"
                        onClick={() => handleReviewApplication(app.id, false, app.name)}
                      >
                        拒绝
                      </Button>
                    </View>
                  </View>
                ))}
              </View>
            </View>
          )}

          {/* 已处理申请 */}
          {applications.filter(a => a.status !== 'pending').length > 0 && (
            <View className="section">
              <Text className="section-title">📋 已处理申请</Text>
              <View className="application-list">
                {applications.filter(a => a.status !== 'pending').slice(0, 10).map(app => (
                  <View key={app.id} className={`application-card ${app.status}`}>
                    <View className="app-info">
                      <View className="app-header">
                        <Text className="app-name">{app.name}</Text>
                        <Text className={`status-tag ${app.status}`}>
                          {app.status === 'approved' ? '已通过' : '已拒绝'}
                        </Text>
                      </View>
                      <Text className="app-email">{app.email}</Text>
                    </View>
                  </View>
                ))}
              </View>
            </View>
          )}
        </>
      )}

      {/* 用户管理 Tab */}
      {activeTab === 'users' && (
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
                      <Text className="user-stat">{user.has_garmin ? '⌚' : '○'} Garmin</Text>
                      <Text className="user-stat">📈 {user.health_records_count}条</Text>
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
              </View>
            </View>
          ))}
        </View>
      </View>
      )}

      <View className="bottom-space" />
    </ScrollView>
  );
}
