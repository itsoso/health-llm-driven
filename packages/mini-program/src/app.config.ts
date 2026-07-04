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
    'pages/workout-guidance/index', // 运动指导
    'pages/heart-rate/index',    // 心率追踪
    'pages/garmin/index',        // Garmin绑定
    'pages/garmin-data/index',   // Garmin数据列表
    'pages/huawei/index',        // 华为手表绑定
    'pages/admin/index',         // 管理后台
    'pages/profile/index',       // 用户画像设置
    'pages/review/index',         // 每日复盘
    'pages/supplements/index',    // 补剂服用
    'pages/diet-recommendation/index', // 饮食推荐
    'pages/water/index',         // 饮水记录
    'pages/weight/index',        // 体重记录
    'pages/privacy/index',       // 隐私保护指引
    'pages/chat/index',            // AI 对话（阿衡 Agent）
    'pages/ai-insights/index',     // AI 健康洞察（测试）
    'pages/mood/index',             // 情绪追踪
    'pages/health-report/index',    // 健康报告
    'pages/body-composition/index', // 身体成分分析
    'pages/health-score/index',     // 健康评分
    'pages/medication/index',       // 用药管理
    'pages/womens-health/index',    // 女性健康
    'pages/illness/index',           // 当前病症追踪
    'pages/llm-analysis/index',      // 多模型分析
    'pages/llm-detail/index',        // 分析详情
    'pages/llm-history/index',       // 分析历史
    'pages/llm-templates/index',     // 模板选择
    'pages/llm-scheduler/index',     // 调度器
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#4f46e5',
    navigationBarTitleText: '自由是自律的泡沫',
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
        pagePath: 'pages/dashboard/index',
        text: '建议',
        iconPath: 'assets/icons/ai-assistant.png',
        selectedIconPath: 'assets/icons/ai-assistant-active.png',
      },
      {
        pagePath: 'pages/checkin/index',
        text: '打卡',
        iconPath: 'assets/icons/checkin.png',
        selectedIconPath: 'assets/icons/checkin-active.png',
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
