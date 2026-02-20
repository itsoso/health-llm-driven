'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';

interface KidsProtectedRouteProps {
  children: React.ReactNode;
  isBoy?: boolean;
}

export default function KidsProtectedRoute({ children, isBoy = false }: KidsProtectedRouteProps) {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading) {
    const bg = isBoy
      ? 'from-blue-50 via-sky-50 to-indigo-50'
      : 'from-pink-50 via-purple-50 to-blue-50';
    const textColor = isBoy ? 'text-blue-500' : 'text-purple-500';
    const icon = isBoy ? '⭐' : '🌟';

    return (
      <div className={`fixed inset-0 z-[100] flex items-center justify-center bg-gradient-to-br ${bg}`}>
        <div className="text-center">
          <div className="text-7xl animate-bounce mb-4">{icon}</div>
          <p className={`text-2xl font-bold ${textColor}`}>加载中...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) return null;

  return <>{children}</>;
}
