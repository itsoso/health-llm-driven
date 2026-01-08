/**
 * API 端点定义
 * 所有前端共用的 API 路径
 */

export const API_ENDPOINTS = {
  // 认证
  AUTH: {
    LOGIN: '/auth/login/json',
    REGISTER: '/auth/register',
    ME: '/auth/me',
    WECHAT_LOGIN: '/wechat/login',
  },
  
  // Garmin 数据
  GARMIN: {
    MY_DATA: '/daily-health/garmin/me',
    SYNC: '/auth/garmin/sync-stream',
    CREDENTIALS: '/auth/garmin/credentials',
    TEST_CONNECTION: '/auth/garmin/test-connection',
  },
  
  // 健康打卡 (鼻炎追踪)
  CHECKIN: {
    CREATE: '/checkin/',
    TODAY: '/checkin/me/today',
    LIST: '/checkin/user',
  },
  
  // 今日建议
  RECOMMENDATION: {
    TODAY: '/daily-recommendation/me',
    REFRESH: '/daily-recommendation/me/refresh',
    CLEAR_CACHE: '/daily-recommendation/me/cache',
  },
  
  // 心率
  HEART_RATE: {
    DAILY: '/heart-rate/me/daily',
    TREND: '/heart-rate/me/trend',
  },
  
  // 运动训练
  WORKOUT: {
    LIST: '/workout/me',
    DETAIL: '/workout/me',
    STATS: '/workout/me/stats',
    SYNC_GARMIN: '/workout/me/sync-garmin',
  },
  
  // 其他
  WEIGHT: {
    LIST: '/weight/me',
    CREATE: '/weight/',
  },
  
  BLOOD_PRESSURE: {
    LIST: '/blood-pressure/me',
    CREATE: '/blood-pressure/',
  },
  
  DIET: {
    LIST: '/diet/me',
    CREATE: '/diet/',
  },
  
  WATER: {
    LIST: '/water/me',
    CREATE: '/water/',
    TODAY_TOTAL: '/water/me/today',
  },
};

