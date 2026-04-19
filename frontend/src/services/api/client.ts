import axios from 'axios';

// frontend/ 只服务 Web (PC 浏览器 + iOS Safari). 原生 App 走 mobile/ 的 React Native 路线.
// Web 版本使用相对路径 /api, 由 next.config.js rewrites 代理到后端.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || '/api';

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器：自动附加认证token
api.interceptors.request.use(
  (config) => {
    // 从localStorage获取token（使用与AuthContext相同的键名）
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('auth_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器：处理401错误（未授权）
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // token过期或无效，清除本地存储并跳转登录
      if (typeof window !== 'undefined') {
        localStorage.removeItem('auth_token');
        // 如果不在登录页，保存当前路径后跳转到登录页
        if (!window.location.pathname.includes('/login')) {
          const destination = window.location.pathname + window.location.search;
          if (destination && destination !== '/') {
            sessionStorage.setItem('redirect_after_login', destination);
          }
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);


export default api;
