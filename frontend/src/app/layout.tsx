import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { Providers } from './providers';
import Navigation from '@/components/Navigation';

const inter = Inter({ 
  subsets: ['latin'],
  display: 'swap', // 使用 swap 显示策略，避免阻塞渲染
  adjustFontFallback: false, // 禁用字体回退调整，减少预加载
});

export const metadata: Metadata = {
  title: '自由是自律的泡沫 - 个人助理 - 个人记录',
  description: '基于LLM的个性化健康管理系统',
  icons: {
    icon: '/favicon.png',
    apple: '/favicon.png',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className={inter.className}>
        <Providers>
          <Navigation />
          {children}
        </Providers>
      </body>
    </html>
  );
}

