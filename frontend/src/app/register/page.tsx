'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';

export default function RegisterPage() {
  const router = useRouter();
  const { register, isAuthenticated } = useAuth();
  
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
    name: '',
  });
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showSuccessModal, setShowSuccessModal] = useState(false);

  // 如果已登录，重定向到首页
  if (isAuthenticated) {
    router.push('/');
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // 验证密码
    if (formData.password !== formData.confirmPassword) {
      setError('两次输入的密码不一致');
      return;
    }

    if (formData.password.length < 6) {
      setError('密码至少需要6个字符');
      return;
    }

    setIsLoading(true);

    const result = await register({
      username: formData.username,
      email: formData.email,
      password: formData.password,
      name: formData.name,
    });
    
    if (result.success) {
      // 显示成功弹窗，引导用户配置 Garmin
      setShowSuccessModal(true);
    } else {
      setError(result.error || '注册失败');
    }
    
    setIsLoading(false);
  };

  const handleGoToSettings = () => {
    router.push('/settings#garmin');
  };

  const handleGoToDashboard = () => {
    router.push('/');
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link href="/" className="inline-flex items-center space-x-2">
            <span className="text-4xl">🏥</span>
            <span className="text-2xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
              健康自律靠AI
            </span>
          </Link>
        </div>

        {/* 注册表单 */}
        <div className="bg-white rounded-2xl shadow-xl p-8 border border-gray-100">
          <h1 className="text-2xl font-bold text-gray-900 text-center mb-6">创建账号</h1>
          
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              ❌ {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                姓名 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                required
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-gray-900"
                placeholder="请输入您的姓名"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                用户名 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                required
                minLength={3}
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-gray-900"
                placeholder="请输入用户名（至少3个字符）"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                邮箱 <span className="text-red-500">*</span>
              </label>
              <input
                type="email"
                required
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-gray-900"
                placeholder="请输入邮箱地址"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                密码 <span className="text-red-500">*</span>
              </label>
              <input
                type="password"
                required
                minLength={6}
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-gray-900"
                placeholder="请输入密码（至少6个字符）"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                确认密码 <span className="text-red-500">*</span>
              </label>
              <input
                type="password"
                required
                value={formData.confirmPassword}
                onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-gray-900"
                placeholder="请再次输入密码"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold rounded-lg hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 transition-all shadow-md"
            >
              {isLoading ? '注册中...' : '立即注册'}
            </button>
          </form>

          <div className="mt-6 text-center">
            <p className="text-gray-600">
              已有账号？{' '}
              <Link href="/login" className="text-indigo-600 hover:text-indigo-700 font-semibold">
                立即登录
              </Link>
            </p>
          </div>
        </div>

        {/* 返回首页 */}
        <div className="text-center mt-6">
          <Link href="/" className="text-gray-500 hover:text-gray-700 text-sm">
            ← 返回首页
          </Link>
        </div>
      </div>

      {/* 注册成功弹窗 */}
      {showSuccessModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-8 transform animate-in fade-in zoom-in duration-300">
            {/* 成功图标 */}
            <div className="text-center mb-6">
              <div className="w-20 h-20 bg-gradient-to-br from-green-400 to-emerald-500 rounded-full flex items-center justify-center mx-auto mb-4 shadow-lg">
                <span className="text-4xl">🎉</span>
              </div>
              <h2 className="text-2xl font-bold text-gray-900">注册成功！</h2>
              <p className="text-gray-600 mt-2">欢迎加入健康自律靠AI</p>
            </div>

            {/* Garmin 提示 */}
            <div className="bg-gradient-to-r from-indigo-50 to-purple-50 rounded-xl p-5 mb-6 border border-indigo-100">
              <div className="flex items-start gap-3">
                <span className="text-3xl">⌚</span>
                <div>
                  <h3 className="font-semibold text-gray-900">配置 Garmin Connect</h3>
                  <p className="text-gray-600 text-sm mt-1">
                    绑定您的 Garmin 账号，自动同步心率、睡眠、运动等健康数据，获取个性化健康建议。
                  </p>
                </div>
              </div>
            </div>

            {/* 按钮 */}
            <div className="space-y-3">
              <button
                onClick={handleGoToSettings}
                className="w-full py-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold rounded-xl hover:from-indigo-700 hover:to-purple-700 transition-all shadow-md flex items-center justify-center gap-2"
              >
                <span>⚙️</span>
                立即配置 Garmin
              </button>
              <button
                onClick={handleGoToDashboard}
                className="w-full py-3 bg-gray-100 text-gray-700 font-medium rounded-xl hover:bg-gray-200 transition-colors"
              >
                稍后再说，先看看
              </button>
            </div>

            <p className="text-center text-gray-400 text-xs mt-4">
              您也可以稍后在「设置」中配置 Garmin 账号
            </p>
          </div>
        </div>
      )}
    </main>
  );
}

