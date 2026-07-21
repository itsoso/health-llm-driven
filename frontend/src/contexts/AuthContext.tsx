'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, ReactNode } from 'react';
import { API_BASE_URL, WEB_SESSION_TOKEN } from '@/services/api/client';

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

  // Web 登录态由同源 HttpOnly Cookie 恢复，JavaScript 不读取持久凭证。
  useEffect(() => {
    fetchUser();
  }, []);

  // 获取用户信息
  const fetchUser = async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        credentials: 'include',
      });

      if (res.ok) {
        // 检查响应内容类型
        const contentType = res.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
          const userData = await res.json();
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
          if (errorData.detail && errorData.detail.includes('审核')) {
            // 未审核用户，保留token和user，但标记为未审核
            const userData = await fetch(`${API_BASE}/auth/me`, {
              credentials: 'include',
            }).then(r => r.ok ? r.json() : null);
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
      setToken(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  // 登录 (使用 useCallback 优化)
  const login = useCallback(async (username: string, password: string): Promise<{ success: boolean; error?: string }> => {
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

      if (res.ok) {
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

  // 注册 (使用 useCallback 优化)
  const register = useCallback(async (data: RegisterData): Promise<{ success: boolean; error?: string }> => {
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
    logout,
    refreshUser,
  }), [user, token, isLoading, login, register, logout, refreshUser]);

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
