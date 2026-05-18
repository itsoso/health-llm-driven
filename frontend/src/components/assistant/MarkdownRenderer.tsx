'use client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';

const DISPLAY_FONT = '"Iowan Old Style", "Noto Serif SC", "Songti SC", serif';

type Variant = 'dark' | 'light';

const styles: Record<Variant, {
  p: string; ul: string; ol: string; li: string;
  h1: string; h2: string; h3: string;
  strong: string; em: string;
  inlineCode: string; codeBlock: string; pre: string;
  blockquote: string; table: string; thead: string;
  tr: string; th: string; td: string; hr: string;
  a: string; aHover: string;
}> = {
  dark: {
    p: 'mb-3 last:mb-0 whitespace-pre-wrap text-zinc-100',
    ul: 'mb-3 ml-5 list-none space-y-2',
    ol: 'mb-3 ml-5 list-decimal space-y-2 marker:text-zinc-500',
    li: 'leading-7 text-zinc-100 relative pl-4 before:content-[""] before:absolute before:left-0 before:top-3 before:h-1 before:w-1 before:rounded-full before:bg-teal-300/70',
    h1: 'mb-3 mt-5 text-lg font-semibold first:mt-0 text-white tracking-wide',
    h2: 'mb-2 mt-5 text-base font-semibold first:mt-0 text-white border-l-2 border-teal-300/70 pl-3',
    h3: 'mb-2 mt-4 text-sm font-semibold first:mt-0 text-zinc-200 uppercase tracking-wider',
    strong: 'font-semibold text-white',
    em: 'italic text-zinc-300',
    inlineCode: 'rounded bg-white/[0.08] px-1.5 py-0.5 font-mono text-[12px] text-teal-300',
    codeBlock: 'my-2 block overflow-x-auto rounded-xl bg-black/40 px-4 py-3 font-mono text-xs text-zinc-200',
    pre: 'my-3 overflow-x-auto rounded-xl bg-black/40 p-4',
    blockquote: 'my-3 rounded-r-lg border-l-2 border-zinc-500/40 bg-white/[0.04] py-2 pl-4 text-sm text-zinc-300',
    table: 'min-w-full overflow-hidden rounded-lg border border-white/10 text-[13px]',
    thead: 'bg-white/[0.04]',
    tr: 'border-b border-white/[0.06] last:border-0',
    th: 'px-3 py-2 text-left font-medium text-zinc-200',
    td: 'px-3 py-2 text-zinc-100',
    hr: 'my-5 border-white/10',
    a: 'text-teal-300 underline-offset-2 underline transition-colors hover:text-teal-200',
    aHover: 'hover:text-teal-200',
  },
  light: {
    p: 'mb-2 last:mb-0',
    ul: 'mb-2 ml-4 list-disc space-y-1',
    ol: 'mb-2 ml-4 list-decimal space-y-1',
    li: 'leading-6',
    h1: 'mb-2 mt-3 text-lg font-bold text-gray-900 first:mt-0',
    h2: 'mb-2 mt-3 text-base font-bold text-gray-900 first:mt-0',
    h3: 'mb-1 mt-2 text-sm font-bold text-gray-800 first:mt-0',
    strong: 'font-semibold text-gray-900',
    em: 'italic text-gray-500',
    inlineCode: 'rounded bg-gray-100 px-1 py-0.5 font-mono text-xs text-emerald-700',
    codeBlock: 'my-2 block overflow-x-auto rounded-xl bg-gray-50 px-3 py-2 font-mono text-xs',
    pre: 'my-2 overflow-x-auto rounded-xl bg-gray-50 p-3',
    blockquote: 'my-2 border-l-3 border-emerald-300 bg-emerald-50/50 py-1 pl-3 italic text-gray-600',
    table: 'min-w-full text-xs border border-gray-200 rounded-lg',
    thead: 'bg-gray-50',
    tr: 'border-b border-gray-100',
    th: 'px-2 py-1.5 text-left font-semibold text-gray-700 border border-gray-200',
    td: 'px-2 py-1.5 border border-gray-200',
    hr: 'my-3 border-gray-200',
    a: 'text-emerald-600 underline hover:text-emerald-800',
    aHover: 'hover:text-emerald-800',
  },
};

// 工具步骤徽章 — running/done/failed 三态
function ToolStep({ name, status }: { name?: string; status?: string }) {
  const s = (status || 'running').toLowerCase();
  const label = s === 'done' ? '完成' : s === 'failed' ? '失败' : '执行中';
  const color = s === 'done'
    ? 'border-emerald-400/30 bg-emerald-400/8 text-emerald-200'
    : s === 'failed'
    ? 'border-rose-400/30 bg-rose-400/8 text-rose-200'
    : 'border-slate-400/30 bg-slate-700/40 text-slate-200';
  const dot = s === 'done' ? 'bg-emerald-400' : s === 'failed' ? 'bg-rose-400' : 'bg-slate-300 animate-pulse';
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium mr-1.5 mb-1.5 ${color}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      <span className="font-mono">{name}</span>
      <span className="opacity-60">·</span>
      <span className="opacity-80">{label}</span>
    </span>
  );
}

export default function MarkdownRenderer({ content, variant = 'light' }: { content: string; variant?: Variant }) {
  const s = styles[variant];
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw]}
      components={{
        p: ({ children }) => <p className={s.p}>{children}</p>,
        ul: ({ children }) => <ul className={s.ul}>{children}</ul>,
        ol: ({ children }) => <ol className={s.ol}>{children}</ol>,
        li: ({ children }) => <li className={s.li}>{children}</li>,
        h1: ({ children }) => <h1 className={s.h1} style={variant === 'dark' ? { fontFamily: DISPLAY_FONT } : undefined}>{children}</h1>,
        h2: ({ children }) => <h2 className={s.h2} style={variant === 'dark' ? { fontFamily: DISPLAY_FONT } : undefined}>{children}</h2>,
        h3: ({ children }) => <h3 className={s.h3} style={variant === 'dark' ? { fontFamily: DISPLAY_FONT } : undefined}>{children}</h3>,
        strong: ({ children }) => <strong className={s.strong}>{children}</strong>,
        em: ({ children }) => <em className={s.em}>{children}</em>,
        code: ({ ...props }: any) => {
          const inline = !props.className?.includes('language-');
          return inline
            ? <code className={s.inlineCode} {...props} />
            : <code className={s.codeBlock} {...props} />;
        },
        pre: ({ children }) => <pre className={s.pre}>{children}</pre>,
        blockquote: ({ children }) => <blockquote className={s.blockquote}>{children}</blockquote>,
        table: ({ children }) => <div className="my-3 overflow-x-auto"><table className={s.table}>{children}</table></div>,
        thead: ({ children }) => <thead className={s.thead}>{children}</thead>,
        ...(variant === 'dark' ? { tbody: ({ children }: any) => <tbody className="bg-transparent">{children}</tbody> } : {}),
        tr: ({ children }) => <tr className={s.tr}>{children}</tr>,
        th: ({ children }) => <th className={s.th}>{children}</th>,
        td: ({ children }) => <td className={s.td}>{children}</td>,
        hr: () => <hr className={s.hr} />,
        a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer" className={s.a}>{children}</a>,
        // @ts-expect-error 自定义元素
        'tool-step': ({ name, status }: any) => <ToolStep name={name} status={status} />,
      }}
    >{content}</ReactMarkdown>
  );
}
