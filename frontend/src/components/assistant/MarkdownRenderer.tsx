'use client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

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
    p: 'mb-3 last:mb-0 whitespace-pre-wrap',
    ul: 'mb-3 ml-5 list-disc space-y-1.5',
    ol: 'mb-3 ml-5 list-decimal space-y-1.5',
    li: 'leading-7',
    h1: 'mb-3 mt-4 text-xl first:mt-0 text-emerald-200',
    h2: 'mb-2 mt-4 text-lg first:mt-0 text-emerald-200',
    h3: 'mb-2 mt-3 text-base first:mt-0 text-emerald-200',
    strong: 'font-semibold text-emerald-200',
    em: 'italic text-slate-200/80',
    inlineCode: 'rounded bg-slate-950/80 px-1.5 py-0.5 font-mono text-xs text-emerald-200',
    codeBlock: 'my-2 block overflow-x-auto rounded-2xl bg-slate-950/90 px-4 py-3 font-mono text-xs',
    pre: 'my-3 overflow-x-auto rounded-2xl bg-slate-950/90 p-4',
    blockquote: 'my-3 rounded-r-2xl border-l-4 border-emerald-400/20 bg-white/[0.03] py-2 pl-4 italic text-slate-200/80',
    table: 'min-w-full overflow-hidden rounded-2xl border border-white/10',
    thead: 'bg-white/[0.06]',
    tr: 'border-b border-white/10 last:border-0',
    th: 'border border-white/10 px-3 py-2 text-left text-sm font-medium text-emerald-200',
    td: 'border border-white/10 px-3 py-2 text-sm',
    hr: 'my-4 border-white/10',
    a: 'text-emerald-200 underline transition-colors hover:text-white',
    aHover: 'hover:text-white',
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

export default function MarkdownRenderer({ content, variant = 'light' }: { content: string; variant?: Variant }) {
  const s = styles[variant];
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
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
        table: ({ children }) => <div className="my-2 overflow-x-auto"><table className={s.table}>{children}</table></div>,
        thead: ({ children }) => <thead className={s.thead}>{children}</thead>,
        ...(variant === 'dark' ? { tbody: ({ children }: any) => <tbody className="bg-slate-950/30">{children}</tbody> } : {}),
        tr: ({ children }) => <tr className={s.tr}>{children}</tr>,
        th: ({ children }) => <th className={s.th}>{children}</th>,
        td: ({ children }) => <td className={s.td}>{children}</td>,
        hr: () => <hr className={s.hr} />,
        a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer" className={s.a}>{children}</a>,
      }}
    >{content}</ReactMarkdown>
  );
}
