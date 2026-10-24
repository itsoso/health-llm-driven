/** @type {import('next').NextConfig} */

// 注: Capacitor 原生 App 已退役（2026-04-19）。iPhone/iPad 走 mobile/ React Native 路线。
// 本配置只服务 Web (PC 浏览器) + iOS Safari.

const nextConfig = {
  reactStrictMode: true,

  // App Router uses Next's bundled React. Recharts 2's react-is 16 cannot
  // recognize its React 19 elements and silently omits the chart children.
  turbopack: {
    resolveAlias: { 'react-is': 'next/dist/compiled/react-is' },
  },
  webpack(config) {
    config.resolve.alias['react-is'] = require.resolve('next/dist/compiled/react-is');
    return config;
  },

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
    const headers = [{
      source: '/:path*',
      headers: [
        { key: 'Content-Security-Policy', value: contentSecurityPolicy },
        { key: 'X-Content-Type-Options', value: 'nosniff' },
        { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        { key: 'Permissions-Policy', value: 'camera=(self), microphone=(self), geolocation=(self)' },
      ],
    }];
    const configuredOrigin = process.env.KBASE_SSO_ORIGIN ?? 'https://kbase.executor.life';
    if (configuredOrigin) {
      const origin = new URL(configuredOrigin);
      if (origin.protocol !== 'https:' || origin.origin !== configuredOrigin || origin.username || origin.password
          || (origin.port && origin.port !== '443')) throw new Error('Invalid KBASE_SSO_ORIGIN');
      headers.push({
        source: '/connect/kbase',
        headers: [
          { key: 'Content-Security-Policy', value: contentSecurityPolicy.replace("form-action 'self'", `form-action 'self' ${origin.origin}`) },
          { key: 'Referrer-Policy', value: 'strict-origin' },
          { key: 'Cache-Control', value: 'no-store' },
        ],
      });
    }
    const eduOrigin = process.env.EDU_SSO_ORIGIN ?? 'https://edu.executor.life';
    if (eduOrigin) {
      const origin = new URL(eduOrigin);
      if (origin.protocol !== 'https:' || origin.origin !== eduOrigin || origin.username || origin.password
          || (origin.port && origin.port !== '443')) throw new Error('Invalid EDU_SSO_ORIGIN');
      headers.push({
        source: '/connect/edu',
        headers: [
          { key: 'Content-Security-Policy', value: contentSecurityPolicy.replace("form-action 'self'", `form-action 'self' ${origin.origin}`) },
          { key: 'Referrer-Policy', value: 'strict-origin' },
          { key: 'Cache-Control', value: 'no-store' },
        ],
      });
    }
    return headers;
  },

  // Web 代理到后端
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
    return [
      {
        source: '/api/v1/auth/sso/edu',
        destination: `${backendUrl}/api/v1/auth/sso/edu`,
      },
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
