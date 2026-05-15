import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

export const dynamic = 'force-dynamic';

interface SharedMessage {
  role: string;
  content: string;
  created_at?: string | null;
}

interface SharedConversation {
  title: string;
  sharer_name?: string | null;
  messages: SharedMessage[];
  created_at: string;
  source_type: string;
}

function apiBaseUrl() {
  const publicBase = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (publicBase && /^https?:\/\//.test(publicBase)) {
    return publicBase.replace(/\/$/, '');
  }
  const backend = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
  return `${backend.replace(/\/$/, '')}/api/v1`;
}

async function loadSharedConversation(shareToken: string): Promise<SharedConversation | null> {
  const res = await fetch(`${apiBaseUrl()}/shared/${shareToken}`, { cache: 'no-store' });
  if (res.status === 404 || res.status === 410) return null;
  if (!res.ok) throw new Error(`load shared conversation failed: ${res.status}`);
  return res.json();
}

function roleLabel(role: string) {
  if (role === 'user') return '用户';
  if (role === 'assistant') return '健康 Agent';
  return '记录';
}

export async function generateMetadata(
  { params }: { params: { shareToken: string } },
): Promise<Metadata> {
  const data = await loadSharedConversation(params.shareToken).catch(() => null);
  const title = data?.title || '健康分享';
  const description = data?.messages?.[0]?.content?.slice(0, 120) || '来自健康 Agent 的分享';
  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: 'article',
    },
  };
}

export default async function SharedPage({ params }: { params: { shareToken: string } }) {
  const data = await loadSharedConversation(params.shareToken);
  if (!data) notFound();

  return (
    <main className="min-h-screen bg-[#F5F7FA] px-4 py-6 text-slate-900">
      <section className="mx-auto max-w-2xl">
        <div className="mb-5">
          <div className="text-xs font-medium text-teal-700">Health Agent Share</div>
          <h1 className="mt-2 text-2xl font-bold leading-tight">{data.title}</h1>
          <div className="mt-2 text-xs text-slate-500">
            {data.sharer_name ? `${data.sharer_name} 分享` : '健康 Agent 分享'}
            {data.created_at ? ` · ${data.created_at.slice(0, 10)}` : ''}
          </div>
        </div>

        <div className="space-y-3">
          {data.messages.map((m, idx) => (
            <article
              key={`${m.role}-${idx}`}
              className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
            >
              <div className="mb-2 text-xs font-semibold text-teal-700">{roleLabel(m.role)}</div>
              <div className="whitespace-pre-wrap text-[15px] leading-7 text-slate-800">
                {m.content}
              </div>
            </article>
          ))}
        </div>

        <footer className="mt-6 rounded-2xl border border-slate-200 bg-white p-4 text-xs leading-5 text-slate-500">
          本页面是用户主动分享的健康管理内容, 不构成诊断、治疗或用药建议。出现明显异常指标或不适症状时, 请咨询医生。
        </footer>
      </section>
    </main>
  );
}
