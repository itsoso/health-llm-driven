'use client';

import RegistrationInvitationPanel from './RegistrationInvitationPanel';

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

interface InvitationTabProps {
  invitationStats: InvitationStats | null;
  invitationCodes: InvitationCode[];
  applications: Application[];
  invitationLoading: boolean;
  statusFilter: string;
  setStatusFilter: (v: string) => void;
  setShowCreateCode: (v: boolean) => void;
  setSelectedApp: (app: Application) => void;
  handleDisableCode: (codeId: number) => void;
  copyToClipboard: (text: string) => void;
  formatDate: (dateStr: string | null) => string;
}

export default function InvitationTab({
  invitationStats,
  invitationCodes,
  applications,
  invitationLoading,
  statusFilter,
  setStatusFilter,
  setShowCreateCode,
  setSelectedApp,
  handleDisableCode,
  copyToClipboard,
  formatDate,
}: InvitationTabProps) {
  return (
    <div className="space-y-6">
      <RegistrationInvitationPanel />

      <div className="pt-2">
        <h2 className="text-lg font-semibold text-white">旧版通用邀请码（不用于手机号注册）</h2>
        <p className="mt-1 text-sm text-purple-200/80">以下邀请码与申请审批仅供旧流程维护，不授予手机号首次注册资格。</p>
      </div>

      {/* Stats Cards */}
      {invitationStats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white/10 backdrop-blur-lg rounded-xl p-4 border border-white/20">
            <div className="text-3xl font-bold text-yellow-400">{invitationStats.applications.pending}</div>
            <div className="text-purple-200 text-sm">待审批申请</div>
          </div>
          <div className="bg-white/10 backdrop-blur-lg rounded-xl p-4 border border-white/20">
            <div className="text-3xl font-bold text-green-400">{invitationStats.applications.approved}</div>
            <div className="text-purple-200 text-sm">已通过</div>
          </div>
          <div className="bg-white/10 backdrop-blur-lg rounded-xl p-4 border border-white/20">
            <div className="text-3xl font-bold text-purple-400">{invitationStats.invitation_codes.active}</div>
            <div className="text-purple-200 text-sm">有效邀请码</div>
          </div>
          <div className="bg-white/10 backdrop-blur-lg rounded-xl p-4 border border-white/20">
            <div className="text-3xl font-bold text-blue-400">{invitationStats.invitation_codes.total_uses}</div>
            <div className="text-purple-200 text-sm">总使用次数</div>
          </div>
        </div>
      )}

      {/* Invitation Code List */}
      <div className="bg-white/10 backdrop-blur-lg rounded-xl border border-white/20 overflow-hidden">
        <div className="p-4 border-b border-white/10 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-white">🎫 旧版邀请码列表</h3>
          <button
            onClick={() => setShowCreateCode(true)}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm"
          >
            + 创建邀请码
          </button>
        </div>

        {invitationLoading ? (
          <div className="p-8 text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400 mx-auto"></div>
          </div>
        ) : invitationCodes.length === 0 ? (
          <div className="p-8 text-center text-purple-200">暂无邀请码</div>
        ) : (
          <div className="divide-y divide-white/10">
            {invitationCodes.map((code) => (
              <div key={code.id} className="p-4 hover:bg-white/5 transition-colors">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <code className="px-3 py-1.5 bg-purple-500/20 text-purple-300 rounded font-mono text-lg">
                      {code.code}
                    </code>
                    <span className={`px-2 py-1 rounded text-xs ${
                      code.is_valid
                        ? 'bg-green-500/20 text-green-400'
                        : 'bg-red-500/20 text-red-400'
                    }`}>
                      {code.is_valid ? '有效' : '已失效'}
                    </span>
                    <span className="text-purple-200 text-sm">
                      {code.used_count}/{code.max_uses} 次
                    </span>
                    {code.note && (
                      <span className="text-gray-400 text-sm">({code.note})</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => copyToClipboard(code.code)}
                      className="px-3 py-1 bg-white/10 text-white rounded hover:bg-white/20 transition-colors text-sm"
                    >
                      复制
                    </button>
                    {code.is_active && (
                      <button
                        onClick={() => handleDisableCode(code.id)}
                        className="px-3 py-1 bg-red-500/20 text-red-400 rounded hover:bg-red-500/30 transition-colors text-sm"
                      >
                        禁用
                      </button>
                    )}
                  </div>
                </div>
                <div className="mt-2 text-gray-400 text-xs">
                  创建于 {formatDate(code.created_at)}
                  {code.creator_name && ` · 创建者: ${code.creator_name}`}
                  {code.expires_at && ` · 过期时间: ${formatDate(code.expires_at)}`}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Application List */}
      <div className="bg-white/10 backdrop-blur-lg rounded-xl border border-white/20 overflow-hidden">
        <div className="p-4 border-b border-white/10">
          <h2 className="text-lg font-semibold text-white mb-4">📝 用户申请</h2>
          <div className="flex items-center gap-2">
            {['pending', 'approved', 'rejected', ''].map((status) => (
              <button
                key={status || 'all'}
                onClick={() => setStatusFilter(status)}
                className={`px-3 py-1 rounded text-sm ${
                  statusFilter === status
                    ? 'bg-purple-500 text-white'
                    : 'bg-white/10 text-gray-300 hover:bg-white/20'
                }`}
              >
                {status === 'pending' ? '待审批' :
                 status === 'approved' ? '已通过' :
                 status === 'rejected' ? '已拒绝' : '全部'}
              </button>
            ))}
          </div>
        </div>

        {invitationLoading ? (
          <div className="p-8 text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400 mx-auto"></div>
          </div>
        ) : applications.length === 0 ? (
          <div className="p-8 text-center text-purple-200">暂无申请记录</div>
        ) : (
          <div className="divide-y divide-white/10">
            {applications.map((app) => (
              <div
                key={app.id}
                className="p-4 hover:bg-white/5 cursor-pointer transition-colors"
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
                      {app.email} · 申请时间：{formatDate(app.created_at)}
                    </div>
                  </div>
                  <span className="text-gray-500">→</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
