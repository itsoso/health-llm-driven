'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef, ReactNode } from 'react';
import { API_BASE_URL, WEB_SESSION_TOKEN } from '@/services/api/client';
import { setAiConsentUser } from '@/services/aiConsent';

const API_BASE = API_BASE_URL;

interface User {
  id: number;
  username: string | null;
  email: string | null;
  phone?: string | null;
  phone_verified_at?: string | null;
  has_password?: boolean;
  name: string;
  birth_date: string | null;
  gender: string | null;
  is_active: boolean;
  is_admin: boolean;
  is_approved: boolean;
  has_garmin_credentials: boolean;
  avatar_url: string | null;
  onboarding_completed?: boolean;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<{ success: boolean; error?: string }>;
  verifyPhoneCode: (phone: string, code: string) => Promise<{ success: boolean; error?: string }>;
  register: (data: RegisterData) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

interface RegisterData {
  username: string;
  email: string;
  password: string;
  name: string;
  invite_code: string;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const authGeneration = useRef(0);
  useEffect(() => {
    setAiConsentUser(user?.id ?? null);
  }, [user?.id]);

  // Web 登录态由同源 HttpOnly Cookie 恢复，JavaScript 不读取持久凭证。
  useEffect(() => {
    fetchUser();
  }, []);

  // 获取用户信息
  const fetchUser = async () => {
    const generation = authGeneration.current;
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        credentials: 'include',
      });

      if (generation !== authGeneration.current) return;
      if (res.ok) {
        // 检查响应内容类型
        const contentType = res.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
          const userData = await res.json();
          if (generation !== authGeneration.current) return;
          setUser(userData);
          setToken(WEB_SESSION_TOKEN);
          // 注: iOS 推送注册已随 Capacitor 退役; iPhone/iPad 推送由 mobile/ (Expo RN) 负责
        } else {
          console.error('获取用户信息：服务器返回非JSON响应');
          setToken(null);
          setUser(null);
        }
      } else if (res.status === 403) {
        // 403可能是未审核，尝试解析错误信息
        try {
          const errorData = await res.json();
          if (generation !== authGeneration.current) return;
          if (errorData.detail && errorData.detail.includes('审核')) {
            // 未审核用户，保留token和user，但标记为未审核
            const userData = await fetch(`${API_BASE}/auth/me`, {
              credentials: 'include',
            }).then(r => r.ok ? r.json() : null);
            if (generation !== authGeneration.current) return;
            if (userData) {
              setUser(userData);
            }
          } else {
            // 其他403错误，清除token
            setToken(null);
            setUser(null);
          }
        } catch {
          // 无法解析错误，清除token
          if (generation !== authGeneration.current) return;
          setToken(null);
          setUser(null);
        }
      } else {
        // Token无效，清除
        setToken(null);
        setUser(null);
      }
    } catch (error) {
      console.error('获取用户信息失败:', error);
      if (generation !== authGeneration.current) return;
      setToken(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  // 登录 (使用 useCallback 优化)
  const login = useCallback(async (username: string, password: string): Promise<{ success: boolean; error?: string }> => {
    const generation = ++authGeneration.current;
    setAiConsentUser(null);
    try {
      const res = await fetch(`${API_BASE}/auth/login/json`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Auth-Transport': 'web-cookie',
        },
        credentials: 'include',
        body: JSON.stringify({ username, password }),
      });

      // 检查响应内容类型
      const contentType = res.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await res.text();
        console.error('服务器返回非JSON响应:', text);
        return { success: false, error: '服务器错误，请稍后重试' };
      }

      const data = await res.json();
      if (generation !== authGeneration.current) return { success: false, error: '登录状态已变化，请重新登录' };

      if (res.ok) {
        setAiConsentUser(data.user.id);
        setToken(WEB_SESSION_TOKEN);
        setUser(data.user);
        return { success: true };
      } else {
        return { success: false, error: data.detail || '登录失败' };
      }
    } catch (error) {
      console.error('登录失败:', error);
      return { success: false, error: '网络错误，请稍后重试' };
    }
  }, []);

  const verifyPhoneCode = useCallback(async (phone: string, code: string): Promise<{ success: boolean; error?: string }> => {
    const generation = ++authGeneration.current;
    setAiConsentUser(null);
    try {
      const res = await fetch(`${API_BASE}/auth/phone/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Auth-Transport': 'web-cookie' },
        credentials: 'include',
        body: JSON.stringify({ phone, code }),
      });
      const data = await res.json();
      if (generation !== authGeneration.current) return { success: false, error: '登录状态已变化，请重新验证' };
      if (!res.ok) {
        const detail = data?.detail;
        return { success: false, error: typeof detail === 'string' ? detail :
          typeof detail?.message === 'string' ? detail.message : '验证码验证失败，请重试' };
      }
      if (data?.outcome !== 'authenticated' || !Number.isInteger(data?.user?.id)) {
        return { success: false, error: '登录服务返回了无法识别的验证结果，请稍后重试' };
      }
      // Read back the HttpOnly session; the response token is never persisted by JavaScript.
      const session = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
      if (!session.ok) return { success: false, error: '登录状态未能建立，请重新验证手机号' };
      const currentUser = await session.json();
      if (generation !== authGeneration.current) return { success: false, error: '登录状态已变化，请重新验证' };
      if (currentUser?.id !== data.user.id) {
        return { success: false, error: '登录账号已变化，请刷新页面后重试' };
      }
      setAiConsentUser(currentUser.id);
      setUser(currentUser);
      setToken(WEB_SESSION_TOKEN);
      return { success: true };
    } catch {
      return { success: false, error: '登录状态验证失败，请检查网络后重试' };
    }
  }, []);

  // 注册 (使用 useCallback 优化)
  const register = useCallback(async (data: RegisterData): Promise<{ success: boolean; error?: string }> => {
    const generation = ++authGeneration.current;
    setAiConsentUser(null);
    try {
      const res = await fetch(`${API_BASE}/auth/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Auth-Transport': 'web-cookie',
        },
        credentials: 'include',
        body: JSON.stringify(data),
      });

      // 检查响应内容类型
      const contentType = res.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await res.text();
        console.error('服务器返回非JSON响应:', text);
        return { success: false, error: '服务器错误，请稍后重试' };
      }

      const result = await res.json();
      if (generation !== authGeneration.current) return { success: false, error: '登录状态已变化，请重新登录' };

      if (res.ok || res.status === 201) {
        // 注册成功，但可能未审核，不设置token
        if (result.access_token) {
          setToken(WEB_SESSION_TOKEN);
          setUser(result.user);
        }
        return { success: true };
      } else {
        return { success: false, error: result.detail || result.message || '注册失败' };
      }
    } catch (error) {
      console.error('注册失败:', error);
      return { success: false, error: '网络错误，请稍后重试' };
    }
  }, []);

  // 登出 (使用 useCallback 优化)
  const logout = useCallback(() => {
    authGeneration.current += 1;
    setAiConsentUser(null);
    setToken(null);
    setUser(null);
    void fetch(`${API_BASE}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });
  }, []);

  // 刷新用户信息 (使用 useCallback 优化)
  const refreshUser = useCallback(async () => {
    if (token) {
      await fetchUser();
    }
  }, [token]);

  // 使用 useMemo 优化 context value，防止不必要的重渲染
  const contextValue = useMemo(() => ({
    user,
    token,
    isLoading,
    isAuthenticated: !!user,
    login,
    register,
    verifyPhoneCode,
    logout,
    refreshUser,
  }), [user, token, isLoading, login, register, verifyPhoneCode, logout, refreshUser]);

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
