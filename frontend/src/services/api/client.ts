import axios from 'axios';
import { AiConsentError, isAiConsentRejection, isAiRequest, requireAiConsent } from '@/services/aiConsent';

// frontend/ 只服务 Web (PC 浏览器 + iOS Safari). 原生 App 走 mobile/ 的 React Native 路线.
// Web 版本使用相对路径 /api, 由 next.config.js rewrites 代理到后端.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || '/api';
export const WEB_SESSION_TOKEN = '__web_cookie_session__';

export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use(async config => {
  if (isAiRequest(config.url, config.method)) await requireAiConsent();
  return config;
});

// 响应拦截器：处理401错误（未授权）
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 403 && isAiConsentRejection(error.response.data)) {
      return Promise.reject(new AiConsentError());
    }
    if (error.response?.status === 401) {
      // HttpOnly 会话无效时跳转登录；浏览器 JavaScript 不接触凭证。
      if (typeof window !== 'undefined') {
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
