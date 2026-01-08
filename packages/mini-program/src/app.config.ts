export default defineAppConfig({
  pages: [
    'pages/index/index',      // 登录页（非 TabBar）
    'pages/dashboard/index',  // 数据面板
    'pages/rhinitis/index',   // 鼻炎追踪
    'pages/settings/index',   // 我的
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
        pagePath: 'pages/dashboard/index',
        text: '数据',
        iconPath: 'assets/icons/chart.png',
        selectedIconPath: 'assets/icons/chart-active.png',
      },
      {
        pagePath: 'pages/rhinitis/index',
        text: '鼻炎',
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
});
