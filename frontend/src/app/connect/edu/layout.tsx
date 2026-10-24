import type { Metadata } from 'next';
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: '登录Edu', referrer: 'strict-origin', robots: { index: false, follow: false } };
export default function EduLoginLayout({ children }: { children: React.ReactNode }) { return children; }
