'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="prose prose-sm max-w-none prose-headings:text-gray-800 prose-p:text-gray-700 prose-p:leading-relaxed prose-strong:text-gray-900 prose-ul:text-gray-700 prose-ol:text-gray-700 prose-li:text-gray-700">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className="text-base font-bold text-gray-800 mt-4 mb-2">{children}</h1>,
          h2: ({ children }) => <h2 className="text-sm font-bold text-gray-800 mt-3 mb-2">{children}</h2>,
          h3: ({ children }) => <h3 className="text-sm font-semibold text-gray-800 mt-3 mb-1.5">{children}</h3>,
          h4: ({ children }) => <h4 className="text-xs font-semibold text-gray-800 mt-2 mb-1">{children}</h4>,
          h5: ({ children }) => <h5 className="text-xs font-semibold text-gray-800 mt-2 mb-1">{children}</h5>,
          h6: ({ children }) => <h6 className="text-xs font-medium text-gray-700 mt-1.5 mb-1">{children}</h6>,
          p: ({ children }) => <p className="text-xs text-gray-700 leading-relaxed my-1.5">{children}</p>,
          ul: ({ children }) => <ul className="list-disc list-inside space-y-0.5 text-xs text-gray-700 my-1.5 ml-1">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal list-inside space-y-0.5 text-xs text-gray-700 my-1.5 ml-1">{children}</ol>,
          li: ({ children }) => <li className="text-xs text-gray-700">{children}</li>,
          strong: ({ children }) => <strong className="text-gray-900 font-semibold">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-indigo-400 pl-2 my-2 text-xs text-gray-600 italic">{children}</blockquote>
          ),
          code: ({ className, children }) => {
            const isInline = !className;
            return isInline ? (
              <code className="bg-gray-100 text-gray-800 px-1 py-0.5 rounded text-xs font-mono">{children}</code>
            ) : (
              <code className="block bg-gray-100 p-2 rounded-lg text-xs font-mono overflow-x-auto">{children}</code>
            );
          },
          pre: ({ children }) => <pre className="bg-gray-100 p-2 rounded-lg overflow-x-auto my-2 text-xs">{children}</pre>,
          hr: () => <hr className="my-3 border-gray-300" />,
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="min-w-full text-xs border-collapse">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-gray-50">{children}</thead>,
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: ({ children }) => <tr className="border-b border-gray-200">{children}</tr>,
          th: ({ children }) => <th className="px-2 py-1.5 text-left text-xs text-gray-700 font-semibold border-b border-gray-300">{children}</th>,
          td: ({ children }) => <td className="px-2 py-1.5 text-xs text-gray-600">{children}</td>,
          a: ({ href, children }) => (
            <a href={href} className="text-xs text-indigo-600 hover:text-indigo-800 underline" target="_blank" rel="noopener noreferrer">{children}</a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
