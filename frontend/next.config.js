/** @type {import('next').NextConfig} */

// 注: Capacitor 原生 App 已退役（2026-04-19）。iPhone/iPad 走 mobile/ React Native 路线。
// 本配置只服务 Web (PC 浏览器) + iOS Safari.

const nextConfig = {
  reactStrictMode: true,

  // 跳过 Server Actions 的 origin 校验（反向代理场景下 origin header 可能缺失）
  experimental: {
    serverActions: {
      allowedOrigins: ['health.executor.life', 'localhost:3000', 'localhost:30001'],
    },
  },

  // 允许内网IP访问开发服务器
  allowedDevOrigins: [
    'http://172.20.102.3:3000',
    'http://192.168.*:3000',
    'http://10.*:3000',
  ],

  async headers() {
    const contentSecurityPolicy = [
      "default-src 'self'",
      "base-uri 'self'",
      "object-src 'none'",
      "frame-ancestors 'none'",
      "form-action 'self'",
      "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: https:",
      "font-src 'self' data:",
      "connect-src 'self' https: wss:",
      "media-src 'self' blob: https:",
      "worker-src 'self' blob:",
      "upgrade-insecure-requests",
    ].join('; ');
    return [{
      source: '/:path*',
      headers: [
        { key: 'Content-Security-Policy', value: contentSecurityPolicy },
        { key: 'X-Content-Type-Options', value: 'nosniff' },
        { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        { key: 'Permissions-Policy', value: 'camera=(self), microphone=(self), geolocation=(self)' },
      ],
    }];
  },

  // Web 代理到后端
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
