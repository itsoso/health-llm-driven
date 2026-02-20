'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useKidsTheme } from '@/contexts/KidsThemeContext';

interface KidsProtectedRouteProps {
  children: React.ReactNode;
}

export default function KidsProtectedRoute({ children }: KidsProtectedRouteProps) {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const { theme } = useKidsTheme();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading) {
    return (
      <div className={`fixed inset-0 z-[100] flex items-center justify-center bg-gradient-to-br ${theme.bg}`}>
        <div className="text-center">
          <div className="text-7xl animate-bounce mb-4">{theme.icon}</div>
          <p className={`text-2xl font-bold ${theme.loadingColor}`}>加载中...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) return null;

  return <>{children}</>;
}
