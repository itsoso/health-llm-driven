export default defineAppConfig({
  pages: [
    'pages/index/index',
    'pages/dashboard/index',
    'pages/rhinitis/index',
    'pages/settings/index',
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#4f46e5',
    navigationBarTitleText: '健康管理',
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

