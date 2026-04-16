import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'life.executor.health',
  appName: '自由是自律的泡沫',
  webDir: 'out',
  server: {
    // 开发时连接到本地后端
    // url: 'http://localhost:3000',
    // cleartext: true,
    
    // 生产环境连接到线上API
    androidScheme: 'https',
    iosScheme: 'https',
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 2000,
      backgroundColor: '#4f46e5',
      showSpinner: true,
      spinnerColor: '#ffffff',
    },
    StatusBar: {
      style: 'dark',
      backgroundColor: '#4f46e5',
    },
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert'],
    },
  },
  ios: {
    contentInset: 'automatic',
    preferredContentMode: 'mobile',
    scheme: '自由是自律的泡沫',
  },
};

export default config;
