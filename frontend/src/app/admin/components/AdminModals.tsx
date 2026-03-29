'use client';

import { UseMutationResult } from '@tanstack/react-query';

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

interface AdminModalsProps {
  // Delete User Modal
  showDeleteConfirm: boolean;
  setShowDeleteConfirm: (v: boolean) => void;
  selectedUser: AdminUser | null;
  setSelectedUser: (u: AdminUser | null) => void;
  deleteUserMutation: UseMutationResult<any, any, number>;

  // Reset Password Modal
  showResetPassword: boolean;
  setShowResetPassword: (v: boolean) => void;
  newPassword: string;
  setNewPassword: (v: string) => void;
  resetPasswordMutation: UseMutationResult<any, any, { userId: number; newPassword: string }>;

  // Create User Modal
  showCreateUser: boolean;
  setShowCreateUser: (v: boolean) => void;
  createUserForm: { username: string; email: string; password: string; name: string; is_approved: boolean };
  setCreateUserForm: (fn: (f: any) => any) => void;
  createUserMutation: UseMutationResult<any, any, any>;

  // Create Invitation Code Modal
  showCreateCode: boolean;
  setShowCreateCode: (v: boolean) => void;
  newCodeNote: string;
  setNewCodeNote: (v: string) => void;
  newCodeMaxUses: number;
  setNewCodeMaxUses: (v: number) => void;
  newCodeExpiresDays: number | null;
  setNewCodeExpiresDays: (v: number | null) => void;
  handleCreateCode: () => void;

  // Application Review Modal
  selectedApp: Application | null;
  setSelectedApp: (app: Application | null) => void;
  reviewNote: string;
  setReviewNote: (v: string) => void;
  handleReview: (approved: boolean) => void;
  formatDate: (dateStr: string | null) => string;
}

export default function AdminModals({
  showDeleteConfirm,
  setShowDeleteConfirm,
  selectedUser,
  setSelectedUser,
  deleteUserMutation,
  showResetPassword,
  setShowResetPassword,
  newPassword,
  setNewPassword,
  resetPasswordMutation,
  showCreateUser,
  setShowCreateUser,
  createUserForm,
  setCreateUserForm,
  createUserMutation,
  showCreateCode,
  setShowCreateCode,
  newCodeNote,
  setNewCodeNote,
  newCodeMaxUses,
  setNewCodeMaxUses,
  newCodeExpiresDays,
  setNewCodeExpiresDays,
  handleCreateCode,
  selectedApp,
  setSelectedApp,
  reviewNote,
  setReviewNote,
  handleReview,
  formatDate,
}: AdminModalsProps) {
  return (
    <>
      {/* Delete User Confirm Modal */}
      {showDeleteConfirm && selectedUser && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowDeleteConfirm(false);
              setSelectedUser(null);
            }
          }}
        >
          <div
            className="bg-slate-800 rounded-xl p-6 max-w-md w-full mx-4 border border-white/20"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-xl font-bold text-white mb-4">确认删除</h3>
            <p className="text-purple-200 mb-6">
              确定要删除用户 <span className="text-white font-semibold">{selectedUser.name}</span> 吗？
              <br />
              <span className="text-red-400 text-sm">此操作将删除该用户的所有数据，且无法恢复。</span>
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setShowDeleteConfirm(false);
                  setSelectedUser(null);
                }}
                disabled={deleteUserMutation.isPending}
                className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                取消
              </button>
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  if (selectedUser && selectedUser.id) {
                    deleteUserMutation.mutate(selectedUser.id);
                  }
                }}
                disabled={deleteUserMutation.isPending || !selectedUser}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {deleteUserMutation.isPending ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reset Password Modal */}
      {showResetPassword && selectedUser && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowResetPassword(false);
              setSelectedUser(null);
              setNewPassword('');
            }
          }}
        >
          <div
            className="bg-slate-800 rounded-xl p-6 max-w-md w-full mx-4 border border-white/20"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-xl font-bold text-white mb-4">🔑 重置密码</h3>
            <p className="text-purple-200 mb-4">
              为用户 <span className="text-white font-semibold">{selectedUser.name}</span>
              {selectedUser.email && <span className="text-gray-400 text-sm"> ({selectedUser.email})</span>} 设置新密码
            </p>
            <div className="mb-6">
              <label className="block text-purple-200 text-sm mb-2">新密码（至少6位）</label>
              <input
                type="text"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="请输入新密码"
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div className="flex gap-3 justify-end">
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setShowResetPassword(false);
                  setSelectedUser(null);
                  setNewPassword('');
                }}
                disabled={resetPasswordMutation.isPending}
                className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                取消
              </button>
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  if (selectedUser && selectedUser.id && newPassword.length >= 6) {
                    resetPasswordMutation.mutate({ userId: selectedUser.id, newPassword });
                  } else if (newPassword.length < 6) {
                    alert('密码长度至少6位');
                  }
                }}
                disabled={resetPasswordMutation.isPending || !selectedUser || newPassword.length < 6}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {resetPasswordMutation.isPending ? '重置中...' : '确认重置'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create User Modal */}
      {showCreateUser && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => { if (e.target === e.currentTarget) setShowCreateUser(false); }}
        >
          <div className="bg-slate-800 rounded-xl p-6 max-w-md w-full mx-4 border border-white/20" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-xl font-bold text-white mb-4">+ 创建用户</h3>
            <div className="space-y-3">
              <div>
                <label className="block text-purple-200 text-sm mb-1">用户名</label>
                <input
                  type="text"
                  value={createUserForm.username}
                  onChange={(e) => setCreateUserForm((f: any) => ({ ...f, username: e.target.value }))}
                  placeholder="用户名（登录用）"
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-purple-200 text-sm mb-1">邮箱</label>
                <input
                  type="email"
                  value={createUserForm.email}
                  onChange={(e) => setCreateUserForm((f: any) => ({ ...f, email: e.target.value }))}
                  placeholder="邮箱地址"
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-purple-200 text-sm mb-1">姓名</label>
                <input
                  type="text"
                  value={createUserForm.name}
                  onChange={(e) => setCreateUserForm((f: any) => ({ ...f, name: e.target.value }))}
                  placeholder="显示名称"
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-purple-200 text-sm mb-1">密码（至少6位）</label>
                <input
                  type="text"
                  value={createUserForm.password}
                  onChange={(e) => setCreateUserForm((f: any) => ({ ...f, password: e.target.value }))}
                  placeholder="初始密码"
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={createUserForm.is_approved}
                  onChange={(e) => setCreateUserForm((f: any) => ({ ...f, is_approved: e.target.checked }))}
                  className="rounded"
                />
                <label className="text-purple-200 text-sm">VIP 用户</label>
              </div>
            </div>
            <div className="flex gap-3 justify-end mt-6">
              <button
                onClick={() => setShowCreateUser(false)}
                className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors"
              >
                取消
              </button>
              <button
                onClick={() => {
                  const { username, email, password, name } = createUserForm;
                  if (!username || !email || !password || !name) { alert('请填写所有字段'); return; }
                  if (password.length < 6) { alert('密码至少6位'); return; }
                  createUserMutation.mutate(createUserForm);
                }}
                disabled={createUserMutation.isPending}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50"
              >
                {createUserMutation.isPending ? '创建中...' : '确认创建'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Invitation Code Modal */}
      {showCreateCode && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowCreateCode(false);
            }
          }}
        >
          <div
            className="bg-slate-800 rounded-xl p-6 max-w-md w-full mx-4 border border-white/20"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-xl font-bold text-white mb-4">创建邀请码</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-purple-200 text-sm mb-2">备注（可选）</label>
                <input
                  type="text"
                  value={newCodeNote}
                  onChange={(e) => setNewCodeNote(e.target.value)}
                  placeholder="例如：给朋友的邀请码"
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-purple-200 text-sm mb-2">最大使用次数</label>
                <input
                  type="number"
                  value={newCodeMaxUses}
                  onChange={(e) => setNewCodeMaxUses(Number(e.target.value))}
                  min={1}
                  max={100}
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-purple-200 text-sm mb-2">过期天数（可选）</label>
                <input
                  type="number"
                  value={newCodeExpiresDays || ''}
                  onChange={(e) => setNewCodeExpiresDays(e.target.value ? Number(e.target.value) : null)}
                  placeholder="留空表示永不过期"
                  min={1}
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
            </div>
            <div className="flex gap-3 justify-end mt-6">
              <button
                onClick={() => setShowCreateCode(false)}
                className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleCreateCode}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Application Review Modal */}
      {selectedApp && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setSelectedApp(null);
              setReviewNote('');
            }
          }}
        >
          <div
            className="bg-slate-800 rounded-xl p-6 max-w-lg w-full mx-4 border border-white/20 max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-xl font-bold text-white mb-4">申请详情</h3>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <span className="text-gray-400 text-sm">姓名</span>
                  <p className="text-white">{selectedApp.name}</p>
                </div>
                <div>
                  <span className="text-gray-400 text-sm">邮箱</span>
                  <p className="text-white">{selectedApp.email}</p>
                </div>
                {selectedApp.phone && (
                  <div>
                    <span className="text-gray-400 text-sm">手机</span>
                    <p className="text-white">{selectedApp.phone}</p>
                  </div>
                )}
                <div>
                  <span className="text-gray-400 text-sm">状态</span>
                  <p className={`${
                    selectedApp.status === 'pending' ? 'text-yellow-400' :
                    selectedApp.status === 'approved' ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {selectedApp.status === 'pending' ? '待审批' :
                     selectedApp.status === 'approved' ? '已通过' : '已拒绝'}
                  </p>
                </div>
              </div>

              {selectedApp.health_questionnaire && (
                <div className="bg-white/5 rounded-lg p-4">
                  <h4 className="text-purple-200 font-medium mb-3">健康问卷</h4>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    {selectedApp.health_questionnaire.age && (
                      <div>
                        <span className="text-gray-400">年龄</span>
                        <p className="text-white">{selectedApp.health_questionnaire.age}岁</p>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.gender && (
                      <div>
                        <span className="text-gray-400">性别</span>
                        <p className="text-white">{selectedApp.health_questionnaire.gender}</p>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.height_cm && (
                      <div>
                        <span className="text-gray-400">身高</span>
                        <p className="text-white">{selectedApp.health_questionnaire.height_cm}cm</p>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.weight_kg && (
                      <div>
                        <span className="text-gray-400">体重</span>
                        <p className="text-white">{selectedApp.health_questionnaire.weight_kg}kg</p>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.exercise_frequency && (
                      <div className="col-span-2">
                        <span className="text-gray-400">运动频率</span>
                        <p className="text-white">{selectedApp.health_questionnaire.exercise_frequency}</p>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.health_goals && selectedApp.health_questionnaire.health_goals.length > 0 && (
                      <div className="col-span-2">
                        <span className="text-gray-400">健康目标</span>
                        <p className="text-white">{selectedApp.health_questionnaire.health_goals.join(', ')}</p>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.wearable_devices && selectedApp.health_questionnaire.wearable_devices.length > 0 && (
                      <div className="col-span-2">
                        <span className="text-gray-400">穿戴设备</span>
                        <p className="text-white">{selectedApp.health_questionnaire.wearable_devices.join(', ')}</p>
                      </div>
                    )}
                    {selectedApp.health_questionnaire.why_join && (
                      <div className="col-span-2">
                        <span className="text-gray-400">加入原因</span>
                        <p className="text-white">{selectedApp.health_questionnaire.why_join}</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {selectedApp.status === 'pending' && (
                <div>
                  <label className="block text-purple-200 text-sm mb-2">审批备注（可选）</label>
                  <textarea
                    value={reviewNote}
                    onChange={(e) => setReviewNote(e.target.value)}
                    placeholder="输入审批备注..."
                    rows={3}
                    className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                  />
                </div>
              )}

              {selectedApp.review_note && (
                <div className="bg-white/5 rounded-lg p-3">
                  <span className="text-gray-400 text-sm">审批备注</span>
                  <p className="text-white">{selectedApp.review_note}</p>
                  {selectedApp.reviewer_name && (
                    <p className="text-gray-400 text-xs mt-1">
                      审批人: {selectedApp.reviewer_name} · {formatDate(selectedApp.reviewed_at)}
                    </p>
                  )}
                </div>
              )}
            </div>

            <div className="flex gap-3 justify-end mt-6">
              <button
                onClick={() => {
                  setSelectedApp(null);
                  setReviewNote('');
                }}
                className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors"
              >
                关闭
              </button>
              {selectedApp.status === 'pending' && (
                <>
                  <button
                    onClick={() => handleReview(false)}
                    className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                  >
                    拒绝
                  </button>
                  <button
                    onClick={() => handleReview(true)}
                    className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
                  >
                    通过
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
