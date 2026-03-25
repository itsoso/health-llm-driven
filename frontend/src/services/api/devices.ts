import api from './client';

export const deviceApi = {
  // 获取支持的设备列表
  getSupportedDevices: () => api.get('/devices/supported'),
  // 获取当前用户绑定的设备
  getMyDevices: () => api.get('/devices/me'),
  // 获取指定设备凭证
  getDeviceCredential: (deviceType: string) => api.get(`/devices/me/${deviceType}`),
  // Apple Health 导入
  importAppleHealth: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/devices/apple/import', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },
  // Apple Health 测试连接
  testAppleConnection: () => api.post('/devices/apple/test-connection'),
  // Apple Health 同步
  syncAppleData: (days: number = 7) => api.post('/devices/apple/sync', { days }),
  // 通用设备同步
  syncDevice: (deviceType: string, days: number = 7) => 
    api.post(`/devices/${deviceType}/sync`, { days }),
  // 同步所有设备
  syncAllDevices: (days: number = 7) => api.post('/devices/sync-all', { days }),
  // 解绑设备
  unbindDevice: (deviceType: string) => api.delete(`/devices/${deviceType}`),
};

// Withings 设备管理
export const withingsApi = {
  // 获取绑定状态
  getStatus: () => api.get('/devices/withings/status'),
  // 获取 OAuth 授权 URL
  getOAuthUrl: () => api.get('/devices/withings/oauth/authorize'),
  // 手动同步数据
  syncData: (days: number = 7) => api.post('/devices/withings/sync', null, { params: { days } }),
  // 查看 Webhook 订阅
  listWebhooks: () => api.get('/devices/withings/webhooks/list'),
  // 手动订阅 Webhook
  subscribeWebhooks: () => api.post('/devices/withings/webhooks/subscribe'),
};

// 运动指导
export const dataCollectionApi = {
  syncGarmin: (userId: number, targetDate: string, accessToken?: string) =>
    api.post('/data-collection/garmin/sync', null, {
      params: { user_id: userId, target_date: targetDate, access_token: accessToken },
    }),
};

// 健康分析
export const dataCollectionStatusApi = {
  getSyncStatus: (userId: number, days: number = 30) =>
    api.get(`/data-collection/garmin/sync-status/${userId}`, { params: { days } }),
  // 使用 /me 端点，自动使用当前登录用户
  getMySyncStatus: (days: number = 30) =>
    api.get('/data-collection/garmin/me/sync-status', { params: { days } }),
};

// 每日建议