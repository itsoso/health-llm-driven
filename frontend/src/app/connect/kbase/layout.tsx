import type { Metadata } from 'next';
export const metadata: Metadata = { title: '登录知识库', referrer: 'strict-origin', robots: { index: false, follow: false } };
export default function KBaseLoginLayout({ children }: { children: React.ReactNode }) { return children; }
