import axios from 'axios';

// 判断是否为原生App环境
// 原生App使用完整的API地址，Web版本使用相对路径（通过Next.js代理）
const isNativeApp = typeof window !== 'undefined' && (
  process.env.NEXT_PUBLIC_IS_NATIVE_APP === 'true' ||
  // Capacitor 环境检测
  (window as any).Capacitor?.isNativePlatform?.()
);

// API基础地址
export const API_BASE_URL = isNativeApp 
  ? 'https://health.executor.life/api'  // 原生App直接调用线上API（新域名）
  : (process.env.NEXT_PUBLIC_API_BASE_URL || '/api');  // Web版本使用代理

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
        // 如果不在登录页，跳转到登录页
        if (!window.location.pathname.includes('/login')) {
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);


export default api;
