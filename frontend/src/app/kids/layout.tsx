'use client';

import { usePathname } from 'next/navigation';
import KidsTabBar from '@/components/kids/KidsTabBar';
import KidsProtectedRoute from '@/components/kids/KidsProtectedRoute';

export default function KidsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <KidsProtectedRoute>
      <div className="fixed inset-0 z-[100] flex flex-col bg-gradient-to-br from-pink-50 via-purple-50 to-blue-50">
        <main className="flex-1 overflow-y-auto pb-24">
          {children}
        </main>
        <KidsTabBar currentPath={pathname} />
      </div>
    </KidsProtectedRoute>
  );
}
