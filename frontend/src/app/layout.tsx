import type { Metadata, Viewport } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { Providers } from './providers';
import Navigation from '@/components/Navigation';
import Footer from '@/components/Footer';
import QuickActionButton from '@/components/QuickActionButton';

const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
  adjustFontFallback: false,
});

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  viewportFit: 'cover',
};

export const metadata: Metadata = {
  title: '个人健康记录 | 个人助理 个人记录',
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
      <body className={`${inter.className} flex flex-col min-h-screen`}>
        <Providers>
          <Navigation />
          <main className="flex-1 mt-16">
            {children}
          </main>
          <Footer />
          <QuickActionButton />
        </Providers>
      </body>
    </html>
  );
}
