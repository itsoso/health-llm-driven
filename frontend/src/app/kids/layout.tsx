'use client';

import { usePathname } from 'next/navigation';
import KidsTabBar from '@/components/kids/KidsTabBar';
import KidsProtectedRoute from '@/components/kids/KidsProtectedRoute';
import { KidsThemeProvider, useKidsTheme } from '@/contexts/KidsThemeContext';

function KidsLayoutContent({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { theme } = useKidsTheme();

  return (
    <KidsProtectedRoute>
      {/* PWA meta tags for standalone app on iPad */}
      <head>
        <link rel="manifest" href="/kids-manifest.json" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="apple-mobile-web-app-title" content="健康&学习小助手" />
        <link rel="apple-touch-icon" sizes="180x180" href="/kids-apple-touch-icon.png" />
        <link rel="icon" type="image/png" sizes="512x512" href="/kids-icon-512.png" />
        <meta name="theme-color" content={theme.isBoy ? '#3b82f6' : '#a855f7'} />
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
      </head>
      <div className={`fixed inset-0 z-[100] flex flex-col bg-gradient-to-br ${theme.bg}`}>
        <main className="flex-1 overflow-hidden">
          {children}
        </main>
        <KidsTabBar currentPath={pathname} />
      </div>
    </KidsProtectedRoute>
  );
}

export default function KidsLayout({ children }: { children: React.ReactNode }) {
  return (
    <KidsThemeProvider>
      <KidsLayoutContent>{children}</KidsLayoutContent>
    </KidsThemeProvider>
  );
}
