export default {
  pages: [
    'pages/index/index',         // 首页
    'pages/ai-assistant/index',  // AI 健康助手
    'pages/dashboard/index',     // 数据面板
    'pages/checkin/index',       // 打卡2.0
    'pages/diet/index',          // 饮食记录（AI识别）
    'pages/environment/index',   // 环境健康
    'pages/disease/index',       // 疾病管理
    'pages/rhinitis/index',      // 鼻炎打卡（旧版）
    'pages/settings/index',      // 我的
    'pages/workout/index',       // 运动训练
    'pages/workout-detail/index',// 运动详情
    'pages/heart-rate/index',    // 心率追踪
    'pages/garmin/index',        // Garmin绑定
    'pages/garmin-data/index',   // Garmin数据列表
    'pages/huawei/index',        // 华为手表绑定
    'pages/admin/index',         // 管理后台
    'pages/profile/index',       // 用户画像设置
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#4f46e5',
    navigationBarTitleText: '自律靠AI',
    navigationBarTextStyle: 'white',
  },
  tabBar: {
    color: '#8a8a8a',
    selectedColor: '#4f46e5',
    backgroundColor: '#ffffff',
    borderStyle: 'black',
    list: [
      {
        pagePath: 'pages/index/index',
        text: '首页',
        iconPath: 'assets/icons/home.png',
        selectedIconPath: 'assets/icons/home-active.png',
      },
      {
        pagePath: 'pages/ai-assistant/index',
        text: 'AI助手',
        iconPath: 'assets/icons/ai-assistant.png',
        selectedIconPath: 'assets/icons/ai-assistant-active.png',
      },
      {
        pagePath: 'pages/dashboard/index',
        text: 'AI建议',
        iconPath: 'assets/icons/chart.png',
        selectedIconPath: 'assets/icons/chart-active.png',
      },
      {
        pagePath: 'pages/checkin/index',
        text: '打卡',
        iconPath: 'assets/icons/nose.png',
        selectedIconPath: 'assets/icons/nose-active.png',
      },
      {
        pagePath: 'pages/settings/index',
        text: '我的',
        iconPath: 'assets/icons/user.png',
        selectedIconPath: 'assets/icons/user-active.png',
      },
    ],
  },
};
