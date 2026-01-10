/**
 * 网络请求封装
 */
import Taro from '@tarojs/taro';

// API 基础地址 - nginx 已配置 /api/ → /api/v1/
const BASE_URL = 'https://health.westwetlandtech.com/api';

// Token 存储 key
const TOKEN_KEY = 'access_token';

/**
 * 获取 Token
 */
export function getToken(): string | null {
  return Taro.getStorageSync(TOKEN_KEY) || null;
}

/**
 * 设置 Token
 */
export function setToken(token: string): void {
  Taro.setStorageSync(TOKEN_KEY, token);
}

/**
 * 清除 Token
 */
export function clearToken(): void {
  Taro.removeStorageSync(TOKEN_KEY);
}

/**
 * 请求配置
 */
interface RequestConfig {
  url: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  data?: any;
  header?: Record<string, string>;
  needAuth?: boolean;
  silent?: boolean; // 静默模式，不显示错误toast
}

/**
 * 响应类型
 */
interface ResponseData<T = any> {
  data: T;
  statusCode: number;
  errMsg: string;
}

/**
 * 封装请求
 */
export async function request<T = any>(config: RequestConfig): Promise<T> {
  const { url, method = 'GET', data, header = {}, needAuth = true, silent = false } = config;

  // 添加认证头
  if (needAuth) {
    const token = getToken();
    if (token) {
      header['Authorization'] = `Bearer ${token}`;
    }
  }

  // 设置 Content-Type
  if (!header['Content-Type']) {
    header['Content-Type'] = 'application/json';
  }

  try {
    const response = await Taro.request<T>({
      url: `${BASE_URL}${url}`,
      method,
      data,
      header,
    });

    const { statusCode, data: responseData } = response;

    // 处理 401 未授权
    if (statusCode === 401) {
      clearToken();
      // 跳转到登录页
      Taro.redirectTo({ url: '/pages/index/index' });
      throw new Error('登录已过期，请重新登录');
    }

    // 处理其他错误
    if (statusCode >= 400) {
      const errorMsg = (responseData as any)?.detail || '请求失败';
      throw new Error(errorMsg);
    }

    return responseData;
  } catch (error: any) {
    console.error('请求失败:', error);
    console.error('请求URL:', `${BASE_URL}${url}`);
    console.error('错误详情:', JSON.stringify(error, null, 2));
    
    if (!silent) {
      let errorMsg = '网络请求失败';
      
      // 处理网络错误
      if (error.errMsg) {
        if (error.errMsg.includes('url not in domain list')) {
          errorMsg = '域名未配置，请在微信公众平台添加合法域名';
        } else if (error.errMsg.includes('fail')) {
          errorMsg = `连接失败: ${error.errMsg}`;
        } else {
          errorMsg = error.errMsg;
        }
      } else if (error.message) {
        errorMsg = error.message;
      }
      
      Taro.showToast({
        title: errorMsg,
        icon: 'none',
        duration: 3000,
      });
    }
    throw error;
  }
}

/**
 * GET 请求
 */
export function get<T = any>(url: string, params?: Record<string, any>): Promise<T> {
  // 将参数拼接到 URL
  if (params) {
    const queryString = Object.entries(params)
      .filter(([_, v]) => v !== undefined && v !== null)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join('&');
    url = queryString ? `${url}?${queryString}` : url;
  }
  return request<T>({ url, method: 'GET' });
}

/**
 * GET 请求（静默模式，不显示错误toast）
 */
export function getSilent<T = any>(url: string, params?: Record<string, any>): Promise<T> {
  if (params) {
    const queryString = Object.entries(params)
      .filter(([_, v]) => v !== undefined && v !== null)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join('&');
    url = queryString ? `${url}?${queryString}` : url;
  }
  return request<T>({ url, method: 'GET', silent: true });
}

/**
 * POST 请求
 */
export function post<T = any>(url: string, data?: any): Promise<T> {
  return request<T>({ url, method: 'POST', data });
}

/**
 * POST 请求（无需认证，用于登录等）
 */
export function postNoAuth<T = any>(url: string, data?: any): Promise<T> {
  return request<T>({ url, method: 'POST', data, needAuth: false });
}

/**
 * PUT 请求
 */
export function put<T = any>(url: string, data?: any): Promise<T> {
  return request<T>({ url, method: 'PUT', data });
}

/**
 * DELETE 请求
 */
export function del<T = any>(url: string): Promise<T> {
  return request<T>({ url, method: 'DELETE' });
}

