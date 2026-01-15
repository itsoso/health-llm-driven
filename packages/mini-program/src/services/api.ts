/**
 * API 服务
 */
import Taro from '@tarojs/taro';
import { get, post, postNoAuth, setToken } from './request';
import { 
  API_ENDPOINTS,
  WechatLoginResponse, 
  GarminData, 
  RhinitisRecord,
  DailyRecommendation 
} from '../types';

/**
 * 微信登录
 * @param nickname 可选的用户昵称
 * @param inviteCode 邀请码（新用户注册时必需）
 */
export async function wechatLogin(nickname?: string, inviteCode?: string): Promise<WechatLoginResponse> {
  // 1. 调用 wx.login 获取 code
  const loginResult = await Taro.login();
  
  if (!loginResult.code) {
    throw new Error('微信登录失败');
  }

  // 2. 发送 code 到后端换取 token（登录不需要认证）
  const response = await postNoAuth<WechatLoginResponse>(API_ENDPOINTS.AUTH.WECHAT_LOGIN, {
    code: loginResult.code,
    nickname: nickname || undefined,
    invite_code: inviteCode || undefined,
  });

  // 3. 保存 token 和用户名（仅当已审核时）
  if (response.access_token) {
    setToken(response.access_token);
  }
  if (response.nickname) {
    Taro.setStorageSync('user_name', response.nickname);
  }

  return response;
}

/**
 * 更新用户昵称
 */
export async function updateUserName(name: string): Promise<{ success: boolean; name: string }> {
  const response = await post<{ success: boolean; name: string }>('/users/me/name', { name });
  if (response.success) {
    Taro.setStorageSync('user_name', response.name);
  }
  return response;
}

/**
 * 获取 Garmin 数据
 */
export async function getGarminData(
  startDate: string,
  endDate: string
): Promise<GarminData[]> {
  // 确保日期格式正确（YYYY-MM-DD）
  const normalizedStartDate = startDate.split('T')[0];
  const normalizedEndDate = endDate.split('T')[0];
  
  return get<GarminData[]>(API_ENDPOINTS.GARMIN.MY_DATA, {
    start_date: normalizedStartDate,
    end_date: normalizedEndDate,
  });
}

/**
 * 获取北京时间的今日日期 (YYYY-MM-DD)
 */
function getBeijingToday(): string {
  const now = new Date();
  // 使用 UTC 时间加上 8 小时得到北京时间
  const utcTime = now.getTime() + now.getTimezoneOffset() * 60 * 1000;
  const beijingTime = new Date(utcTime + 8 * 60 * 60 * 1000);
  
  const year = beijingTime.getFullYear();
  const month = String(beijingTime.getMonth() + 1).padStart(2, '0');
  const day = String(beijingTime.getDate()).padStart(2, '0');
  
  return `${year}-${month}-${day}`;
}

/**
 * 获取今日 Garmin 数据（使用北京时间）
 */
export async function getTodayGarminData(): Promise<GarminData | null> {
  const today = getBeijingToday();
  console.log('[API] 获取今日 Garmin 数据, 日期:', today);
  
  const data = await getGarminData(today, today);
  console.log('[API] 获取到的数据:', data.length > 0 ? `steps=${data[0].steps}, battery=${data[0].body_battery_most_charged}` : '无数据');
  return data.length > 0 ? data[0] : null;
}

/**
 * 获取今日建议
 */
export async function getDailyRecommendation(): Promise<DailyRecommendation> {
  return get<DailyRecommendation>(API_ENDPOINTS.RECOMMENDATION.TODAY);
}

/**
 * 鼻炎追踪 - 获取今日记录
 */
export async function getTodayRhinitis(): Promise<RhinitisRecord | null> {
  try {
    return await get<RhinitisRecord>(API_ENDPOINTS.CHECKIN.TODAY);
  } catch (e) {
    return null;
  }
}

/**
 * 鼻炎追踪 - 保存记录
 */
export async function saveRhinitisRecord(
  data: Partial<RhinitisRecord>
): Promise<RhinitisRecord> {
  const today = new Date().toISOString().split('T')[0];
  return post<RhinitisRecord>(API_ENDPOINTS.CHECKIN.CREATE, {
    checkin_date: today,
    ...data,
  });
}

/**
 * 检查是否绑定了 Garmin
 */
export async function checkGarminBinding(userId: number): Promise<{
  has_garmin: boolean;
  garmin_email?: string;
  sync_enabled: boolean;
  credentials_valid: boolean;
}> {
  return get(`/wechat/check-binding/${userId}`);
}

/**
 * 同步当前用户的 Garmin 数据（使用已保存的凭据）
 */
export async function syncMyGarminData(days: number = 1): Promise<{
  status: string;
  message: string;
  success_count?: number;
  error_count?: number;
  activities_count?: number;
}> {
  return post(`/data-collection/garmin/me/sync?days=${days}`, {});
}
