/** @type {import('next').NextConfig} */

// 是否为原生App构建（iOS/Android）
const isNativeApp = process.env.BUILD_TARGET === 'native';

const nextConfig = {
  reactStrictMode: true,
  
  // 原生App构建使用静态导出
  ...(isNativeApp && {
    output: 'export',
    trailingSlash: true,
    images: {
      unoptimized: true,
    },
  }),
  
  // 允许内网IP访问开发服务器
  allowedDevOrigins: [
    'http://172.20.102.3:3000',
    'http://192.168.*:3000',
    'http://10.*:3000',
  ],
  
  // 环境变量传递到客户端
  env: {
    NEXT_PUBLIC_IS_NATIVE_APP: isNativeApp ? 'true' : 'false',
    NEXT_PUBLIC_API_BASE_URL: isNativeApp 
      ? 'https://health.westwetlandtech.com/api' 
      : '',
  },
  
  // Web 版本使用代理
  ...(!isNativeApp && {
    async rewrites() {
      // 后端API地址，可通过环境变量配置
      const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
      return [
        {
          source: '/api/:path*',
          destination: `${backendUrl}/api/v1/:path*`,
        },
      ];
    },
  }),
};

module.exports = nextConfig;

