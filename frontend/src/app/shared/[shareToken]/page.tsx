import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import MarkdownRenderer from '@/components/assistant/MarkdownRenderer';
import { normalizeSharedAgentContent } from './contentNormalizer';
import OpenInAppButton from './OpenInAppButton';
import { buildSharedMetadata, isSensitiveSharedConversation } from './sharePrivacy';
import SharedMessageImages from './SharedMessageImages';

export const dynamic = 'force-dynamic';

interface SharedMessage {
  role: string;
  content: string;
  created_at?: string | null;
  image_url?: string | null;
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

async function loadSharedConversation(
  shareToken: string,
  { countView = true }: { countView?: boolean } = {},
): Promise<SharedConversation | null> {
  const params = countView ? '' : '?count_view=false';
  const res = await fetch(`${apiBaseUrl()}/shared/${shareToken}${params}`, { cache: 'no-store' });
  if (res.status === 404 || res.status === 410) return null;
  if (!res.ok) throw new Error(`load shared conversation failed: ${res.status}`);
  return res.json();
}

function roleLabel(role: string) {
  if (role === 'user') return '用户';
  if (role === 'assistant') return '健康小巴';
  return '记录';
}

export async function generateMetadata(
  { params }: { params: Promise<{ shareToken: string }> },
): Promise<Metadata> {
  const { shareToken } = await params;
  const data = await loadSharedConversation(shareToken, { countView: false }).catch(() => null);
  const title = data?.title || '健康分享';
  const sharedMetadata = buildSharedMetadata({
    title,
    sensitive: data ? isSensitiveSharedConversation(data) : false,
    firstMessage: data?.messages?.[0]?.content,
  });
  return {
    title,
    description: sharedMetadata.description,
    robots: { index: false, follow: false },
    openGraph: {
      title,
      description: sharedMetadata.description,
      type: 'article',
      images: [{ url: sharedMetadata.imageUrl, width: 512, height: 512, alt: title }],
    },
    twitter: {
      card: 'summary',
      title,
      description: sharedMetadata.description,
      images: [sharedMetadata.imageUrl],
    },
  };
}

export default async function SharedPage({
  params,
  searchParams,
}: {
  params: Promise<{ shareToken: string }>;
  searchParams?: Promise<{ reveal?: string }>;
}) {
  const { shareToken } = await params;
  const query: { reveal?: string } = searchParams ? await searchParams : {};
  const revealSensitiveContent = query.reveal === '1';
  const data = await loadSharedConversation(shareToken, { countView: !revealSensitiveContent });
  if (!data) notFound();

  const isSensitive = isSensitiveSharedConversation(data);

  return (
    <main className="min-h-screen bg-[#F5F7FA] px-4 py-6 text-slate-900">
      <section className="mx-auto max-w-2xl">
        <div className="mb-5">
          <div className="text-xs font-medium text-teal-700">Health Agent Share</div>
          <h1 className="mt-2 text-2xl font-bold leading-tight">{data.title}</h1>
          <div className="mt-2 text-xs text-slate-500">
            {data.sharer_name ? `${data.sharer_name} 分享` : '健康小巴分享'}
            {data.created_at ? ` · ${data.created_at.slice(0, 10)}` : ''}
          </div>
        </div>

        {isSensitive && !revealSensitiveContent ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950 shadow-sm">
            <div className="text-base font-semibold">这条分享可能包含健康敏感信息</div>
            <p className="mt-2">
              内容可能涉及基因、检查、疾病、用药或心理健康信息。请确认你信任分享来源，并避免继续转发给无关人员。
            </p>
            <a
              href={`/shared/${shareToken}?reveal=1`}
              className="mt-4 inline-flex rounded-lg bg-amber-900 px-4 py-2 text-sm font-medium text-white hover:bg-amber-800"
            >
              确认查看内容
            </a>
          </div>
        ) : (
          <div className="space-y-3">
            {data.messages.map((m, idx) => (
              <article
                key={`${m.role}-${idx}`}
                className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
              >
                <div className="mb-2 text-xs font-semibold text-teal-700">{roleLabel(m.role)}</div>
                <div className="text-[15px] leading-7 text-slate-800">
                  {m.role === 'user' ? (
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  ) : (
                    <MarkdownRenderer content={normalizeSharedAgentContent(m.content)} variant="light" />
                  )}
                </div>
                <SharedMessageImages imageUrl={m.image_url} />
              </article>
            ))}
          </div>
        )}

        <footer className="mt-6 space-y-3">
          {(!isSensitive || revealSensitiveContent) && <OpenInAppButton shareToken={shareToken} />}
          <div className="rounded-2xl border border-slate-200 bg-white p-4 text-xs leading-5 text-slate-500">
            本页面是用户主动分享的健康管理内容, 不构成诊断、治疗或用药建议。出现明显异常指标或不适症状时, 请咨询医生。
          </div>
        </footer>
      </section>
    </main>
  );
}
