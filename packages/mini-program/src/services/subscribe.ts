/**
 * 微信小程序订阅消息服务
 * 
 * 使用说明：
 * 1. 在微信公众平台配置订阅消息模板
 * 2. 将模板ID配置到 TEMPLATE_IDS
 * 3. 在合适的时机调用 requestSubscribe 请求用户授权
 * 4. 授权后调用 saveSubscribeSettings 保存到后端
 */

import Taro from '@tarojs/taro';
import { request, get, put } from './request';

// ============ 订阅消息模板配置 ============
// 注意：以下模板ID需要在微信公众平台申请后替换
// 申请路径：微信公众平台 -> 功能 -> 订阅消息 -> 选用模板

export const TEMPLATE_IDS = {
  // 健康提醒模板（用于喝水、洗鼻、运动等提醒）
  HEALTH_REMINDER: 'rit2hRtAH4d1mjtyiUMMLVN3VYzWXEbUzqeT3iSv-SI',
  
  // 早间简报模板
  MORNING_BRIEFING: 'A-R8QFFj1OSPPH3WHil6FupmtihH94aBikFFSnUnAPg',
  
  // 健康预警模板
  HEALTH_ALERT: 'JCSm2jb6-78Bl3UmTA1JdfFNtv5WQnetA6JfS3SoTSg',
  
  // 目标进度模板
  GOAL_PROGRESS: 'buawjDAdCSdbILS5JbrSTPSvSlYB0_rPTMpxK4t3xaE',
  
  // 周报模板
  WEEKLY_REPORT: 'sjiGrcujQj4FMN-iQlKEqzuAYknzOBNFMpnz15pwWPo',
};

// 模板类型映射（用于显示）
export const TEMPLATE_NAMES: Record<string, string> = {
  HEALTH_REMINDER: '健康提醒',
  MORNING_BRIEFING: '早间简报',
  HEALTH_ALERT: '健康预警',
  GOAL_PROGRESS: '目标进度',
  WEEKLY_REPORT: '周报通知',
};

// ============ 订阅状态管理 ============

interface SubscribeResult {
  success: boolean;
  acceptedTemplates: string[];
  rejectedTemplates: string[];
  error?: string;
}

/**
 * 请求订阅消息授权
 * 
 * @param templateKeys 要订阅的模板key数组，如 ['HEALTH_REMINDER', 'MORNING_BRIEFING']
 * @returns 订阅结果
 * 
 * 注意：
 * - 微信限制每次最多请求3个模板
 * - 用户拒绝后，同一模板7天内不会再弹窗
 * - 建议在用户主动操作时调用（如点击"开启提醒"按钮）
 */
export async function requestSubscribe(templateKeys: string[]): Promise<SubscribeResult> {
  // 过滤出有效的模板ID
  const templateIds = templateKeys
    .map(key => TEMPLATE_IDS[key as keyof typeof TEMPLATE_IDS])
    .filter(id => id && id.length > 0);
  
  if (templateIds.length === 0) {
    console.warn('[订阅] 没有配置有效的模板ID');
    return {
      success: false,
      acceptedTemplates: [],
      rejectedTemplates: templateKeys,
      error: '订阅模板未配置，请联系管理员',
    };
  }
  
  // 微信限制每次最多3个模板
  const limitedIds = templateIds.slice(0, 3);
  
  try {
    const res = await Taro.requestSubscribeMessage({
      tmplIds: limitedIds,
    });
    
    const acceptedTemplates: string[] = [];
    const rejectedTemplates: string[] = [];
    
    // 解析结果
    templateKeys.forEach(key => {
      const templateId = TEMPLATE_IDS[key as keyof typeof TEMPLATE_IDS];
      if (templateId && res[templateId] === 'accept') {
        acceptedTemplates.push(key);
      } else {
        rejectedTemplates.push(key);
      }
    });
    
    console.log('[订阅] 授权结果:', { acceptedTemplates, rejectedTemplates });
    
    // 如果有成功订阅的，保存到后端
    if (acceptedTemplates.length > 0) {
      await saveSubscribeSettings(acceptedTemplates);
    }
    
    return {
      success: acceptedTemplates.length > 0,
      acceptedTemplates,
      rejectedTemplates,
    };
    
  } catch (error: any) {
    console.error('[订阅] 授权失败:', error);
    
    // 处理特定错误
    let errorMsg = '订阅失败，请重试';
    if (error.errMsg?.includes('cancel')) {
      errorMsg = '您取消了订阅';
    } else if (error.errMsg?.includes('reject')) {
      errorMsg = '您拒绝了订阅，可在设置中重新开启';
    }
    
    return {
      success: false,
      acceptedTemplates: [],
      rejectedTemplates: templateKeys,
      error: errorMsg,
    };
  }
}

/**
 * 请求所有推荐的订阅模板
 * 用于首次使用或设置页面的"一键开启"
 */
export async function requestAllSubscriptions(): Promise<SubscribeResult> {
  const allKeys = Object.keys(TEMPLATE_IDS).filter(
    key => TEMPLATE_IDS[key as keyof typeof TEMPLATE_IDS]
  );
  
  if (allKeys.length === 0) {
    Taro.showToast({
      title: '订阅模板未配置',
      icon: 'none',
    });
    return {
      success: false,
      acceptedTemplates: [],
      rejectedTemplates: [],
      error: '订阅模板未配置',
    };
  }
  
  // 分批请求（每次最多3个）
  const results: SubscribeResult = {
    success: false,
    acceptedTemplates: [],
    rejectedTemplates: [],
  };
  
  for (let i = 0; i < allKeys.length; i += 3) {
    const batch = allKeys.slice(i, i + 3);
    const batchResult = await requestSubscribe(batch);
    
    results.acceptedTemplates.push(...batchResult.acceptedTemplates);
    results.rejectedTemplates.push(...batchResult.rejectedTemplates);
    
    if (batchResult.success) {
      results.success = true;
    }
    
    // 如果用户取消，停止后续请求
    if (batchResult.error?.includes('取消')) {
      break;
    }
  }
  
  return results;
}

/**
 * 保存订阅设置到后端
 */
export async function saveSubscribeSettings(acceptedTemplateKeys: string[]): Promise<boolean> {
  try {
    // 构建模板ID映射
    const templateIds: Record<string, string> = {};
    acceptedTemplateKeys.forEach(key => {
      const templateId = TEMPLATE_IDS[key as keyof typeof TEMPLATE_IDS];
      if (templateId) {
        // 转换为后端使用的类型名称
        const typeMap: Record<string, string> = {
          HEALTH_REMINDER: 'reminder',
          MORNING_BRIEFING: 'morning_briefing',
          HEALTH_ALERT: 'health_alert',
          GOAL_PROGRESS: 'goal_progress',
          WEEKLY_REPORT: 'weekly_report',
        };
        const backendType = typeMap[key] || key.toLowerCase();
        templateIds[backendType] = templateId;
      }
    });
    
    await request({
      url: '/wechat/subscribe/settings',
      method: 'POST',
      data: {
        template_ids: templateIds,
        enabled: true,
      },
    });
    
    console.log('[订阅] 设置已保存到后端');
    return true;
    
  } catch (error) {
    console.error('[订阅] 保存设置失败:', error);
    return false;
  }
}

/**
 * 获取当前订阅设置
 */
export async function getSubscribeSettings(): Promise<{
  enabled: boolean;
  templateIds: Record<string, string>;
} | null> {
  try {
    const res = await request({
      url: '/wechat/subscribe/settings',
      method: 'GET',
    });
    return res as any;
  } catch (error) {
    console.error('[订阅] 获取设置失败:', error);
    return null;
  }
}

/**
 * 检查订阅消息是否可用
 * 用于判断是否显示订阅相关UI
 */
export function isSubscribeAvailable(): boolean {
  // 检查是否有配置模板ID
  const hasTemplates = Object.values(TEMPLATE_IDS).some(id => id && id.length > 0);
  return hasTemplates;
}

/**
 * 显示订阅引导
 * 在合适的时机调用，引导用户开启订阅
 */
export async function showSubscribeGuide(): Promise<void> {
  const result = await Taro.showModal({
    title: '开启消息提醒',
    content: '开启后，您将收到健康提醒、早间简报等通知，帮助您更好地管理健康。',
    confirmText: '立即开启',
    cancelText: '稍后再说',
  });
  
  if (result.confirm) {
    const subscribeResult = await requestAllSubscriptions();
    
    if (subscribeResult.success) {
      Taro.showToast({
        title: `已开启${subscribeResult.acceptedTemplates.length}项提醒`,
        icon: 'success',
      });
    } else if (subscribeResult.error) {
      Taro.showToast({
        title: subscribeResult.error,
        icon: 'none',
      });
    }
  }
}

/**
 * 请求单次订阅（用于特定场景）
 * 例如：用户完成打卡后，请求下次提醒的订阅
 */
export async function requestSingleSubscribe(
  templateKey: keyof typeof TEMPLATE_IDS,
  silent: boolean = false
): Promise<boolean> {
  const result = await requestSubscribe([templateKey]);
  
  if (!silent) {
    if (result.success) {
      Taro.showToast({
        title: '提醒已开启',
        icon: 'success',
      });
    } else if (result.error && !result.error.includes('取消')) {
      Taro.showToast({
        title: result.error,
        icon: 'none',
      });
    }
  }
  
  return result.success;
}
