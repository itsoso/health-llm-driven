'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api/client';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import UserManagementTab from './components/UserManagementTab';
import GarminSyncTab from './components/GarminSyncTab';
import InvitationTab from './components/InvitationTab';
import ObservabilityTab from './components/ObservabilityTab';
import AdminModals from './components/AdminModals';

interface AdminUser {
  id: number;
  username: string | null;
  email: string | null;
  name: string;
  gender: string | null;
  is_active: boolean;
  is_admin: boolean;
  is_approved: boolean;
  created_at: string | null;
  last_activity: string | null;
  has_garmin: boolean;
  health_records_count: number;
  medical_exams_count: number;
}

interface AdminStats {
  total_users: number;
  active_users: number;
  admin_users: number;
  users_with_garmin: number;
  total_health_records: number;
  total_medical_exams: number;
  new_users_today: number;
  new_users_week: number;
}

interface UserListResponse {
  users: AdminUser[];
  total: number;
  page: number;
  page_size: number;
}

interface GarminSyncUser {
  user_id: number;
  username: string | null;
  name: string | null;
  garmin_email: string;
  sync_enabled: boolean;
  credentials_valid: boolean;
  last_error: string | null;
  error_count: number;
  last_sync_at: string | null;
  latest_data_date: string | null;
  total_records: number;
}

interface GarminSyncStatus {
  total_configured_users: number;
  valid_credentials: number;
  invalid_credentials: number;
  users: GarminSyncUser[];
}

interface SyncResult {
  total_users: number;
  success_users: number;
  failed_users: number;
  details: Array<{
    user_id: number;
    success: boolean;
    success_count: number;
    error_count: number;
    message: string;
  }>;
}

interface ClearCacheResult {
  message: string;
  deleted_count: number;
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

export default function AdminPage() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<'users' | 'garmin' | 'invitation' | 'observability' | 'performance'>('users');
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showResetPassword, setShowResetPassword] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [createUserForm, setCreateUserForm] = useState({ username: '', email: '', password: '', name: '', is_approved: true });
  const [syncDays, setSyncDays] = useState(3);
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [syncingUserId, setSyncingUserId] = useState<number | null>(null);
  const pageSize = 15;

  // Invitation state
  const [invitationCodes, setInvitationCodes] = useState<InvitationCode[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [invitationStats, setInvitationStats] = useState<InvitationStats | null>(null);
  const [selectedApp, setSelectedApp] = useState<Application | null>(null);
  const [reviewNote, setReviewNote] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('pending');
  const [showCreateCode, setShowCreateCode] = useState(false);
  const [newCodeNote, setNewCodeNote] = useState('');
  const [newCodeMaxUses, setNewCodeMaxUses] = useState(10);
  const [newCodeExpiresDays, setNewCodeExpiresDays] = useState<number | null>(null);
  const [invitationLoading, setInvitationLoading] = useState(false);

  // Auth check
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    } else if (!authLoading && isAuthenticated && !user?.is_admin) {
      router.push('/');
    }
  }, [authLoading, isAuthenticated, user, router]);

  // Fetch invitation data
  const fetchInvitationData = useCallback(async () => {
    setInvitationLoading(true);
    try {
      const [appsRes, codesRes, statsRes] = await Promise.all([
        api.get(`/invitation/applications${statusFilter ? `?status=${statusFilter}` : ''}`),
        api.get('/invitation/codes'),
        api.get('/invitation/stats'),
      ]);
      setApplications(appsRes.data);
      setInvitationCodes(codesRes.data);
      setInvitationStats(statsRes.data);
    } catch (error) {
      console.error('Failed to fetch invitation data:', error);
    } finally {
      setInvitationLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    if (activeTab === 'invitation' && isAuthenticated && user?.is_admin) {
      fetchInvitationData();
    }
  }, [activeTab, isAuthenticated, user, fetchInvitationData]);

  // Queries
  const { data: stats, isLoading: statsLoading } = useQuery<AdminStats>({
    queryKey: ['admin-stats'],
    queryFn: async () => { const res = await api.get('/admin/stats'); return res.data; },
    enabled: isAuthenticated && user?.is_admin,
  });

  const { data: userList, isLoading: usersLoading, refetch } = useQuery<UserListResponse>({
    queryKey: ['admin-users', currentPage, searchTerm],
    queryFn: async () => {
      const params = new URLSearchParams({ page: currentPage.toString(), page_size: pageSize.toString() });
      if (searchTerm) params.append('search', searchTerm);
      const res = await api.get(`/admin/users?${params}`);
      return res.data;
    },
    enabled: isAuthenticated && user?.is_admin,
  });

  const { data: garminSyncStatus, isLoading: garminStatusLoading, refetch: refetchGarminStatus } = useQuery<GarminSyncStatus>({
    queryKey: ['admin-garmin-sync-status'],
    queryFn: async () => { const res = await api.get('/admin/garmin/sync-status'); return res.data; },
    enabled: isAuthenticated && user?.is_admin && activeTab === 'garmin',
  });

  // Mutations
  const setAdminMutation = useMutation({
    mutationFn: async ({ userId, isAdmin }: { userId: number; isAdmin: boolean }) => {
      const res = await api.put(`/admin/users/${userId}/admin`, { is_admin: isAdmin }); return res.data;
    },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin-users'] }); queryClient.invalidateQueries({ queryKey: ['admin-stats'] }); },
  });

  const setActiveMutation = useMutation({
    mutationFn: async ({ userId, isActive }: { userId: number; isActive: boolean }) => {
      const res = await api.put(`/admin/users/${userId}/active`, { is_active: isActive }); return res.data;
    },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin-users'] }); queryClient.invalidateQueries({ queryKey: ['admin-stats'] }); },
  });

  const deleteUserMutation = useMutation({
    mutationFn: async (userId: number) => { const res = await api.delete(`/admin/users/${userId}`); return res.data; },
    onSuccess: (data) => {
      setShowDeleteConfirm(false); setSelectedUser(null);
      alert(data.message || '用户删除成功');
      queryClient.invalidateQueries({ queryKey: ['admin-users'] }); queryClient.invalidateQueries({ queryKey: ['admin-stats'] });
    },
    onError: (error: any) => {
      console.error('删除用户失败:', error);
      alert(`❌ ${error?.response?.data?.detail || error?.message || '删除用户失败，请稍后重试'}`);
      setShowDeleteConfirm(false); setSelectedUser(null);
    },
  });

  const resetPasswordMutation = useMutation({
    mutationFn: async ({ userId, newPassword }: { userId: number; newPassword: string }) => {
      const res = await api.put(`/admin/users/${userId}/password`, { new_password: newPassword }); return res.data;
    },
    onSuccess: (data) => { setShowResetPassword(false); setSelectedUser(null); setNewPassword(''); alert(data.message || '密码重置成功'); },
    onError: (error: any) => {
      console.error('重置密码失败:', error);
      alert(`❌ ${error?.response?.data?.detail || error?.message || '重置密码失败，请稍后重试'}`);
    },
  });

  const syncAllMutation = useMutation({
    mutationFn: async (days: number) => { const res = await api.post(`/admin/garmin/sync-all?days=${days}`); return res.data; },
    onSuccess: (data) => { setSyncResult(data); queryClient.invalidateQueries({ queryKey: ['admin-garmin-sync-status'] }); },
  });

  const syncUserMutation = useMutation({
    mutationFn: async ({ userId, days }: { userId: number; days: number }) => {
      setSyncingUserId(userId); const res = await api.post(`/admin/garmin/sync-user/${userId}?days=${days}`); return res.data;
    },
    onSuccess: () => { setSyncingUserId(null); queryClient.invalidateQueries({ queryKey: ['admin-garmin-sync-status'] }); },
    onError: () => { setSyncingUserId(null); },
  });

  const resetCredentialsMutation = useMutation({
    mutationFn: async (userId: number) => { const res = await api.post(`/admin/garmin/reset-credentials/${userId}`); return res.data; },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin-garmin-sync-status'] }); },
  });

  const toggleSyncMutation = useMutation({
    mutationFn: async ({ userId, syncEnabled }: { userId: number; syncEnabled: boolean }) => {
      const res = await api.put(`/admin/garmin/sync-enabled/${userId}`, { sync_enabled: syncEnabled }); return res.data;
    },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin-garmin-sync-status'] }); },
  });

  const clearUserCacheMutation = useMutation({
    mutationFn: async (userId: number) => { const res = await api.delete(`/admin/users/${userId}/cache`); return res.data as ClearCacheResult; },
    onSuccess: (data) => { alert(`${data.message}（删除 ${data.deleted_count} 条记录）`); },
  });

  const clearNoDataCacheMutation = useMutation({
    mutationFn: async () => { const res = await api.delete('/admin/cache/no-data'); return res.data as ClearCacheResult; },
    onSuccess: (data) => { alert(`${data.message}（删除 ${data.deleted_count} 条记录）`); },
  });

  const clearAllCacheMutation = useMutation({
    mutationFn: async () => { const res = await api.delete('/admin/cache/all'); return res.data as ClearCacheResult; },
    onSuccess: (data) => { alert(`${data.message}（删除 ${data.deleted_count} 条记录）`); },
  });

  const setVipMutation = useMutation({
    mutationFn: async ({ userId, isApproved }: { userId: number; isApproved: boolean }) => {
      const res = await api.put(`/admin/users/${userId}/approve`, { is_approved: isApproved }); return res.data;
    },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin-users'] }); },
  });

  const createUserMutation = useMutation({
    mutationFn: async (form: typeof createUserForm) => { const res = await api.post('/admin/users/create', form); return res.data; },
    onSuccess: (data) => {
      setShowCreateUser(false); setCreateUserForm({ username: '', email: '', password: '', name: '', is_approved: true });
      queryClient.invalidateQueries({ queryKey: ['admin-users'] }); alert(data.message || '用户创建成功');
    },
    onError: (error: any) => { alert(`❌ ${error?.response?.data?.detail || '创建失败'}`); },
  });

  // Invitation handlers
  const handleReview = async (approved: boolean) => {
    if (!selectedApp) return;
    try {
      await api.post(`/invitation/applications/${selectedApp.id}/review`, { approved, note: reviewNote || null });
      setSelectedApp(null); setReviewNote(''); fetchInvitationData();
    } catch (error) { console.error('Failed to review:', error); alert('审批失败，请重试'); }
  };

  const handleCreateCode = async () => {
    try {
      await api.post('/invitation/codes', { note: newCodeNote || null, max_uses: newCodeMaxUses, expires_days: newCodeExpiresDays });
      setShowCreateCode(false); setNewCodeNote(''); setNewCodeMaxUses(10); setNewCodeExpiresDays(null); fetchInvitationData();
    } catch (error) { console.error('Failed to create code:', error); alert('创建失败，请重试'); }
  };

  const handleDisableCode = async (codeId: number) => {
    if (!confirm('确定要禁用此邀请码吗？')) return;
    try { await api.delete(`/invitation/codes/${codeId}`); fetchInvitationData(); }
    catch (error) { console.error('Failed to disable code:', error); alert('操作失败，请重试'); }
  };

  const copyToClipboard = (text: string) => { navigator.clipboard.writeText(text); alert('已复制到剪贴板'); };

  // Loading state
  if (authLoading || !isAuthenticated || !user?.is_admin) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-400 mx-auto mb-4"></div>
          <p className="text-purple-200">验证权限中...</p>
        </div>
      </div>
    );
  }

  const handleSearch = (e: React.FormEvent) => { e.preventDefault(); setCurrentPage(() => 1); refetch(); };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <main className="min-h-screen p-8 bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 pt-4">
      <div className="max-w-7xl mx-auto">
        {/* Page Title */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">🛡️ 管理后台</h1>
          <p className="text-purple-200">管理用户、Garmin同步和邀请码</p>
        </div>

        {/* Tab Navigation */}
        <div className="flex gap-2 mb-6">
          <button onClick={() => setActiveTab('users')} className={`px-6 py-2 rounded-lg font-medium transition-colors ${activeTab === 'users' ? 'bg-purple-600 text-white' : 'bg-white/10 text-purple-200 hover:bg-white/20'}`}>
            👥 用户管理
          </button>
          <button onClick={() => setActiveTab('garmin')} className={`px-6 py-2 rounded-lg font-medium transition-colors ${activeTab === 'garmin' ? 'bg-purple-600 text-white' : 'bg-white/10 text-purple-200 hover:bg-white/20'}`}>
            ⌚ Garmin同步
          </button>
          <button onClick={() => setActiveTab('invitation')} className={`px-6 py-2 rounded-lg font-medium transition-colors ${activeTab === 'invitation' ? 'bg-purple-600 text-white' : 'bg-white/10 text-purple-200 hover:bg-white/20'}`}>
            🎫 邀请码管理
          </button>
          <button onClick={() => setActiveTab('observability')} className={`px-6 py-2 rounded-lg font-medium transition-colors ${activeTab === 'observability' ? 'bg-purple-600 text-white' : 'bg-white/10 text-purple-200 hover:bg-white/20'}`}>
            📊 观察期看板
          </button>
          <button onClick={() => router.push('/admin/performance')} className="px-6 py-2 rounded-lg font-medium transition-colors bg-white/10 text-purple-200 hover:bg-white/20">
            📈 性能监控
          </button>
          <button onClick={() => router.push('/admin/llm-performance')} className="px-6 py-2 rounded-lg font-medium transition-colors bg-white/10 text-purple-200 hover:bg-white/20">
            🤖 LLM 性能
          </button>
          <button onClick={() => router.push('/admin/system-map')} className="px-6 py-2 rounded-lg font-medium transition-colors bg-white/10 text-purple-200 hover:bg-white/20">
            🗺️ 系统地图
          </button>
          <button onClick={() => router.push('/admin/knowledge')} className="px-6 py-2 rounded-lg font-medium transition-colors bg-white/10 text-purple-200 hover:bg-white/20">
            📚 KB Review
          </button>
        </div>

        {/* Tab Content */}
        {activeTab === 'users' && (
          <UserManagementTab
            stats={stats}
            statsLoading={statsLoading}
            userList={userList}
            usersLoading={usersLoading}
            currentPage={currentPage}
            setCurrentPage={setCurrentPage}
            searchTerm={searchTerm}
            setSearchTerm={setSearchTerm}
            handleSearch={handleSearch}
            setShowCreateUser={setShowCreateUser}
            currentUserId={user?.id}
            setVipMutation={setVipMutation}
            setAdminMutation={setAdminMutation}
            setActiveMutation={setActiveMutation}
            clearUserCacheMutation={clearUserCacheMutation}
            clearNoDataCacheMutation={clearNoDataCacheMutation}
            clearAllCacheMutation={clearAllCacheMutation}
            setSelectedUser={setSelectedUser}
            setShowResetPassword={setShowResetPassword}
            setShowDeleteConfirm={setShowDeleteConfirm}
            formatDate={formatDate}
            pageSize={pageSize}
          />
        )}

        {activeTab === 'garmin' && (
          <GarminSyncTab
            garminSyncStatus={garminSyncStatus}
            garminStatusLoading={garminStatusLoading}
            refetchGarminStatus={refetchGarminStatus}
            syncDays={syncDays}
            setSyncDays={setSyncDays}
            syncResult={syncResult}
            syncingUserId={syncingUserId}
            syncAllMutation={syncAllMutation}
            syncUserMutation={syncUserMutation}
            resetCredentialsMutation={resetCredentialsMutation}
            toggleSyncMutation={toggleSyncMutation}
            formatDate={formatDate}
          />
        )}

        {activeTab === 'observability' && <ObservabilityTab />}

        {activeTab === 'invitation' && (
          <InvitationTab
            invitationStats={invitationStats}
            invitationCodes={invitationCodes}
            applications={applications}
            invitationLoading={invitationLoading}
            statusFilter={statusFilter}
            setStatusFilter={setStatusFilter}
            setShowCreateCode={setShowCreateCode}
            setSelectedApp={setSelectedApp}
            handleDisableCode={handleDisableCode}
            copyToClipboard={copyToClipboard}
            formatDate={formatDate}
          />
        )}
      </div>

      {/* Modals */}
      <AdminModals
        showDeleteConfirm={showDeleteConfirm}
        setShowDeleteConfirm={setShowDeleteConfirm}
        selectedUser={selectedUser}
        setSelectedUser={setSelectedUser}
        deleteUserMutation={deleteUserMutation}
        showResetPassword={showResetPassword}
        setShowResetPassword={setShowResetPassword}
        newPassword={newPassword}
        setNewPassword={setNewPassword}
        resetPasswordMutation={resetPasswordMutation}
        showCreateUser={showCreateUser}
        setShowCreateUser={setShowCreateUser}
        createUserForm={createUserForm}
        setCreateUserForm={setCreateUserForm}
        createUserMutation={createUserMutation}
        showCreateCode={showCreateCode}
        setShowCreateCode={setShowCreateCode}
        newCodeNote={newCodeNote}
        setNewCodeNote={setNewCodeNote}
        newCodeMaxUses={newCodeMaxUses}
        setNewCodeMaxUses={setNewCodeMaxUses}
        newCodeExpiresDays={newCodeExpiresDays}
        setNewCodeExpiresDays={setNewCodeExpiresDays}
        handleCreateCode={handleCreateCode}
        selectedApp={selectedApp}
        setSelectedApp={setSelectedApp}
        reviewNote={reviewNote}
        setReviewNote={setReviewNote}
        handleReview={handleReview}
        formatDate={formatDate}
      />
    </main>
  );
}
