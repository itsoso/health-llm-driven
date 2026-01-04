'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

interface User {
  id: number;
  username: string | null;
  email: string | null;
  name: string;
  birth_date: string | null;
  gender: string | null;
  is_active: boolean;
  has_garmin_credentials: boolean;
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
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // 初始化时从localStorage加载token
  useEffect(() => {
    const storedToken = localStorage.getItem('auth_token');
    if (storedToken) {
      setToken(storedToken);
      fetchUser(storedToken);
    } else {
      setIsLoading(false);
    }
  }, []);

  // 获取用户信息
  const fetchUser = async (authToken: string) => {
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        headers: {
          'Authorization': `Bearer ${authToken}`,
        },
      });
      
      if (res.ok) {
        const userData = await res.json();
        setUser(userData);
      } else {
        // Token无效，清除
        localStorage.removeItem('auth_token');
        setToken(null);
        setUser(null);
      }
    } catch (error) {
      console.error('获取用户信息失败:', error);
      localStorage.removeItem('auth_token');
      setToken(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  // 登录
  const login = async (username: string, password: string): Promise<{ success: boolean; error?: string }> => {
    try {
      const res = await fetch(`${API_BASE}/auth/login/json`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      });

      const data = await res.json();

      if (res.ok) {
        setToken(data.access_token);
        setUser(data.user);
        localStorage.setItem('auth_token', data.access_token);
        return { success: true };
      } else {
        return { success: false, error: data.detail || '登录失败' };
      }
    } catch (error) {
      console.error('登录失败:', error);
      return { success: false, error: '网络错误，请稍后重试' };
    }
  };

  // 注册
  const register = async (data: RegisterData): Promise<{ success: boolean; error?: string }> => {
    try {
      const res = await fetch(`${API_BASE}/auth/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      });

      const result = await res.json();

      if (res.ok) {
        setToken(result.access_token);
        setUser(result.user);
        localStorage.setItem('auth_token', result.access_token);
        return { success: true };
      } else {
        return { success: false, error: result.detail || '注册失败' };
      }
    } catch (error) {
      console.error('注册失败:', error);
      return { success: false, error: '网络错误，请稍后重试' };
    }
  };

  // 登出
  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('auth_token');
  };

  // 刷新用户信息
  const refreshUser = async () => {
    if (token) {
      await fetchUser(token);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated: !!user,
        login,
        register,
        logout,
        refreshUser,
      }}
    >
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

