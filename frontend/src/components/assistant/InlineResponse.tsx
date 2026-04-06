'use client';
import { forwardRef } from 'react';
import MarkdownRenderer from './MarkdownRenderer';

interface InlineResponseProps {
  question: string;
  answer: string;
  loading: boolean;
  onClose: () => void;
}

const InlineResponse = forwardRef<HTMLDivElement, InlineResponseProps>(
  ({ question, answer, loading, onClose }, ref) => (
    <div ref={ref} className="rounded-2xl border border-emerald-100 shadow-lg overflow-hidden" style={{ background: 'linear-gradient(to bottom, #f0fdf4, #ffffff)' }}>
      <div className="px-5 pt-4 pb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-lg bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center">
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" /></svg>
          </div>
          <span className="text-xs text-emerald-700 bg-emerald-50 rounded-full px-2.5 py-0.5 font-medium">{question}</span>
        </div>
        <button onClick={onClose}
          className="w-6 h-6 rounded-full flex items-center justify-center text-gray-300 hover:text-gray-500 hover:bg-gray-100 transition-all text-sm">×</button>
      </div>
      <div className="px-5 pb-4 text-sm text-gray-700 leading-relaxed max-h-[50vh] overflow-y-auto">
        {answer ? (
          <MarkdownRenderer content={answer} variant="light" />
        ) : loading ? (
          <div className="flex items-center gap-2 py-2 text-emerald-500">
            <div className="flex gap-1">
              <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <span className="text-xs">思考中...</span>
          </div>
        ) : null}
      </div>
      {loading && answer && (
        <div className="px-5 pb-3 flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
          <span className="text-[11px] text-emerald-500">生成中...</span>
        </div>
      )}
    </div>
  )
);

InlineResponse.displayName = 'InlineResponse';
export default InlineResponse;
