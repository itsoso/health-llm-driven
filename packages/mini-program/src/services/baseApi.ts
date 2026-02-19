/**
 * base.executor.life API 请求封装
 * 复用 health.executor.life 的 JWT token
 */
import Taro from '@tarojs/taro';
import { getToken } from './request';

const BASE_API_URL = 'https://base.executor.life/api';

interface BaseRequestConfig {
  url: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  data?: any;
  params?: Record<string, any>;
  timeout?: number;
}

export async function baseRequest<T = any>(config: BaseRequestConfig): Promise<T> {
  const { url, method = 'GET', data, params, timeout = 120000 } = config;

  const token = getToken();
  const header: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    header['Authorization'] = `Bearer ${token}`;
  }

  // 构建完整 URL
  let finalUrl = `${BASE_API_URL}${url}`;
  if (params) {
    const qs = Object.entries(params)
      .filter(([_, v]) => v !== undefined && v !== null)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
      .join('&');
    if (qs) finalUrl += `?${qs}`;
  }

  try {
    const response = await Taro.request<T>({
      url: finalUrl,
      method,
      data,
      header,
      timeout,
    });

    if (response.statusCode === 401) {
      // 不清除 token，避免影响 health.executor.life 的登录状态
      throw new Error('分析服务认证失败，请重新登录');
    }

    if (response.statusCode >= 400) {
      const errorMsg = (response.data as any)?.error
        || (response.data as any)?.detail
        || '请求失败';
      throw new Error(errorMsg);
    }

    return response.data;
  } catch (error: any) {
    if (error?.message?.includes('认证失败')) {
      throw error;
    }

    const errMsg = error?.errMsg || error?.message || '网络请求失败';
    console.error('[baseApi] 请求失败:', finalUrl, errMsg);
    throw new Error(errMsg);
  }
}
