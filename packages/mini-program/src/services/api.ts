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
 */
export async function wechatLogin(): Promise<WechatLoginResponse> {
  // 1. 调用 wx.login 获取 code
  const loginResult = await Taro.login();
  
  if (!loginResult.code) {
    throw new Error('微信登录失败');
  }

  // 2. 获取用户信息（可选）
  let nickname: string | undefined;
  let avatarUrl: string | undefined;
  
  try {
    // 注意：getUserProfile 需要用户主动触发
    // 这里仅作示例，实际应在按钮点击时调用
  } catch (e) {
    console.log('获取用户信息失败，使用默认值');
  }

  // 3. 发送 code 到后端换取 token（登录不需要认证）
  const response = await postNoAuth<WechatLoginResponse>(API_ENDPOINTS.AUTH.WECHAT_LOGIN, {
    code: loginResult.code,
    nickname,
    avatar_url: avatarUrl,
  });

  // 4. 保存 token
  setToken(response.access_token);

  return response;
}

/**
 * 获取 Garmin 数据
 */
export async function getGarminData(
  startDate: string,
  endDate: string
): Promise<GarminData[]> {
  return get<GarminData[]>(API_ENDPOINTS.GARMIN.MY_DATA, {
    start_date: startDate,
    end_date: endDate,
  });
}

/**
 * 获取今日 Garmin 数据
 */
export async function getTodayGarminData(): Promise<GarminData | null> {
  const today = new Date().toISOString().split('T')[0];
  const data = await getGarminData(today, today);
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
