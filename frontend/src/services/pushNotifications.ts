/**
 * iOS 原生推送注册服务 (Capacitor)
 *
 * Agent Native Phase 1: 注册 APNs device token，
 * 上传到后端 /notification/bind/ios，使后端的
 * PushService 能通过 APNs 发送健康告警推送。
 *
 * 仅在 Native 平台生效，Web 端静默跳过。
 */
import { Capacitor } from '@capacitor/core';
import api from './api/client';

let registered = false;

export async function registerPushNotifications() {
  if (!Capacitor.isNativePlatform() || registered) return;

  try {
    // 动态导入——Web 端不加载 native 插件
    const { PushNotifications } = await import('@capacitor/push-notifications');

    // 请求权限
    const permission = await PushNotifications.requestPermissions();
    if (permission.receive !== 'granted') {
      console.log('[Push] 用户拒绝推送权限');
      return;
    }

    // 注册 APNs
    await PushNotifications.register();

    // 获取 device token 并上传到后端
    PushNotifications.addListener('registration', async (token) => {
      console.log('[Push] Device token:', token.value.slice(0, 10) + '...');
      try {
        await api.post('/notification/bind/ios', { device_token: token.value });
        console.log('[Push] Token 已上传到后端');
      } catch (e) {
        console.error('[Push] Token 上传失败:', e);
      }
    });

    PushNotifications.addListener('registrationError', (error) => {
      console.error('[Push] 注册失败:', error);
    });

    // App 在前台时收到推送
    PushNotifications.addListener('pushNotificationReceived', (notification) => {
      console.log('[Push] 前台收到:', notification.title);
      // 前台时不需要额外处理——Capacitor presentationOptions 已配置 alert/sound/badge
    });

    // 用户点击推送通知
    PushNotifications.addListener('pushNotificationActionPerformed', (action) => {
      const data = action.notification.data;
      console.log('[Push] 用户点击:', data);
      // 跳转到相关页面
      if (data?.url) {
        window.location.href = data.url;
      } else if (data?.type === 'health_alert') {
        window.location.href = '/ai-assistant';
      }
    });

    registered = true;
    console.log('[Push] 推送注册完成');
  } catch (e) {
    // Web 端或插件未安装时静默失败
    console.log('[Push] 推送不可用（可能是 Web 环境）:', (e as Error).message);
  }
}
