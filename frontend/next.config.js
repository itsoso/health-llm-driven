/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  
  // 允许内网IP访问开发服务器
  allowedDevOrigins: [
    'http://172.20.102.3:3000',
    'http://192.168.*:3000',
    'http://10.*:3000',
  ],
  
  async rewrites() {
    // 后端API地址，可通过环境变量配置
    // 内网部署时可设置为内网IP，如: BACKEND_URL=http://192.168.1.100:8000
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

