'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { extractErrorMsg } from './GarminSection';

const API_BASE = '/api';

interface UserProfileSectionProps {
  token: string | null;
  setMessage: (msg: { type: 'success' | 'error'; text: string } | null) => void;
}

export default function UserProfileSection({ token, setMessage }: UserProfileSectionProps) {
  const { user, logout, refreshUser } = useAuth();

  // Web登录绑定状态
  const [showBindForm, setShowBindForm] = useState(false);
  const [bindEmail, setBindEmail] = useState('');
  const [bindPassword, setBindPassword] = useState('');
  const [bindLoading, setBindLoading] = useState(false);
  // 修改密码
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changePwdLoading, setChangePwdLoading] = useState(false);

  // 用户名编辑状态
  const [isEditingName, setIsEditingName] = useState(false);
  const [editName, setEditName] = useState('');

  // 更新用户名
  const updateNameMutation = useMutation({
    mutationFn: async (name: string) => {
      const res = await fetch(`${API_BASE}/auth/me`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ name }),
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || '更新失败');
      }
      return res.json();
    },
    onSuccess: () => {
      refreshUser();
      setIsEditingName(false);
      setMessage({ type: 'success', text: '用户名已更新' });
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: error.message });
    },
  });

  return (
    <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-gray-100">
      <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
        👤 账户信息
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="text-sm text-gray-500">用户名</label>
          <p className="text-gray-900 font-medium">{user?.username || '-'}</p>
        </div>
        <div>
          <label className="text-sm text-gray-500">邮箱</label>
          {user?.email ? (
            <p className="text-gray-900 font-medium">{user.email}</p>
          ) : (
            <div className="flex items-center gap-2">
              <p className="text-gray-400">未绑定</p>
              <button
                onClick={() => setShowBindForm(!showBindForm)}
                className="text-indigo-500 hover:text-indigo-600 text-sm"
              >
                绑定邮箱
              </button>
            </div>
          )}
        </div>
        <div>
          <label className="text-sm text-gray-500">姓名</label>
          {isEditingName ? (
            <div className="flex items-center gap-2 mt-1">
              <input
                type="text"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="flex-1 p-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                placeholder="请输入姓名"
                autoFocus
              />
              <button
                onClick={() => {
                  if (editName.trim()) {
                    updateNameMutation.mutate(editName.trim());
                  }
                }}
                disabled={!editName.trim() || updateNameMutation.isPending}
                className="px-3 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 disabled:opacity-50 text-sm"
              >
                {updateNameMutation.isPending ? '保存中...' : '保存'}
              </button>
              <button
                onClick={() => {
                  setIsEditingName(false);
                  setEditName('');
                }}
                className="px-3 py-2 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 text-sm"
              >
                取消
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <p className="text-gray-900 font-medium">{user?.name || '-'}</p>
              <button
                onClick={() => {
                  setEditName(user?.name || '');
                  setIsEditingName(true);
                }}
                className="text-indigo-500 hover:text-indigo-600 text-sm"
              >
                ✏️ 编辑
              </button>
            </div>
          )}
        </div>
        <div>
          <label className="text-sm text-gray-500">账户状态</label>
          <p className="text-green-600 font-medium">
            {user?.is_active ? '✓ 已激活' : '✗ 未激活'}
          </p>
        </div>
      </div>
      {/* 绑定Web登录表单 */}
      {showBindForm && !user?.email && (
        <div className="mt-4 pt-4 border-t">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">绑定邮箱和密码（用于Web端登录）</h3>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">邮箱地址</label>
              <input
                type="email"
                value={bindEmail}
                onChange={(e) => setBindEmail(e.target.value)}
                placeholder="请输入邮箱"
                className="w-full p-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">设置密码（至少6位）</label>
              <input
                type="password"
                value={bindPassword}
                onChange={(e) => setBindPassword(e.target.value)}
                placeholder="请设置登录密码"
                className="w-full p-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  if (!bindEmail.trim() || !bindPassword.trim()) {
                    setMessage({ type: 'error', text: '请填写邮箱和密码' });
                    return;
                  }
                  if (bindPassword.length < 6) {
                    setMessage({ type: 'error', text: '密码至少6位' });
                    return;
                  }
                  setBindLoading(true);
                  try {
                    const res = await fetch(`${API_BASE}/auth/bind-web-login`, {
                      method: 'POST',
                      headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`,
                      },
                      body: JSON.stringify({ email: bindEmail, password: bindPassword }),
                    });
                    const data = await res.json();
                    if (res.ok) {
                      setMessage({ type: 'success', text: '绑定成功！现在可以使用邮箱和密码在Web端登录' });
                      setShowBindForm(false);
                      setBindEmail('');
                      setBindPassword('');
                      refreshUser();
                    } else {
                      setMessage({ type: 'error', text: data.detail || '绑定失败' });
                    }
                  } catch {
                    setMessage({ type: 'error', text: '网络错误，请重试' });
                  } finally {
                    setBindLoading(false);
                  }
                }}
                disabled={bindLoading}
                className="px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 disabled:opacity-50 text-sm"
              >
                {bindLoading ? '绑定中...' : '确认绑定'}
              </button>
              <button
                onClick={() => {
                  setShowBindForm(false);
                  setBindEmail('');
                  setBindPassword('');
                }}
                className="px-4 py-2 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 text-sm"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 修改密码 */}
      {user?.email && (
        <div className="mt-4 pt-4 border-t">
          <button
            onClick={() => setShowChangePassword(!showChangePassword)}
            className="text-sm text-indigo-600 hover:text-indigo-800"
          >
            {showChangePassword ? '取消修改密码' : '修改密码'}
          </button>
          {showChangePassword && (
            <div className="mt-3 space-y-3">
              <div>
                <label className="text-xs text-gray-500 mb-1 block">当前密码</label>
                <input
                  type="password"
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                  placeholder="请输入当前密码"
                  className="w-full p-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">新密码（至少6位）</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="请输入新密码"
                  className="w-full p-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">确认新密码</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="请再次输入新密码"
                  className="w-full p-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                />
              </div>
              <button
                onClick={async () => {
                  if (!oldPassword.trim()) {
                    setMessage({ type: 'error', text: '请输入当前密码' });
                    return;
                  }
                  if (newPassword.length < 6) {
                    setMessage({ type: 'error', text: '新密码至少6位' });
                    return;
                  }
                  if (newPassword !== confirmPassword) {
                    setMessage({ type: 'error', text: '两次输入的新密码不一致' });
                    return;
                  }
                  setChangePwdLoading(true);
                  try {
                    const res = await fetch(`${API_BASE}/auth/change-password`, {
                      method: 'POST',
                      headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`,
                      },
                      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
                    });
                    const data = await res.json();
                    if (res.ok) {
                      setMessage({ type: 'success', text: '密码修改成功' });
                      setShowChangePassword(false);
                      setOldPassword('');
                      setNewPassword('');
                      setConfirmPassword('');
                    } else {
                      setMessage({ type: 'error', text: data.detail || '修改失败' });
                    }
                  } catch {
                    setMessage({ type: 'error', text: '网络错误，请重试' });
                  } finally {
                    setChangePwdLoading(false);
                  }
                }}
                disabled={changePwdLoading}
                className="px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 disabled:opacity-50 text-sm"
              >
                {changePwdLoading ? '修改中...' : '确认修改'}
              </button>
            </div>
          )}
        </div>
      )}

      <div className="mt-4 pt-4 border-t">
        <button
          onClick={logout}
          className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
        >
          退出登录
        </button>
      </div>
    </div>
  );
}
