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
    <div ref={ref} className="rounded-2xl bg-white overflow-hidden" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      <div className="px-4 pt-4 pb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-lg flex items-center justify-center" style={{ background: '#007AFF' }}>
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" /></svg>
          </div>
          <span className="text-xs rounded-full px-2.5 py-0.5 font-medium" style={{ color: '#007AFF', background: '#F2F2F7' }}>{question}</span>
        </div>
        <button onClick={onClose}
          className="w-6 h-6 rounded-full flex items-center justify-center hover:bg-gray-100 transition-all text-sm"
          style={{ color: '#AEAEB2' }}>×</button>
      </div>
      <div className="px-4 pb-4 text-sm leading-relaxed max-h-[50vh] overflow-y-auto" style={{ color: '#1C1C1E' }}>
        {answer ? (
          <MarkdownRenderer content={answer} variant="light" />
        ) : loading ? (
          <div className="flex items-center gap-2 py-2" style={{ color: '#007AFF' }}>
            <div className="flex gap-1">
              <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#007AFF', animationDelay: '0ms' }} />
              <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#007AFF', animationDelay: '150ms' }} />
              <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#007AFF', animationDelay: '300ms' }} />
            </div>
            <span className="text-xs">思考中...</span>
          </div>
        ) : null}
      </div>
      {loading && answer && (
        <div className="px-4 pb-3 flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: '#007AFF' }} />
          <span className="text-[11px]" style={{ color: '#007AFF' }}>生成中...</span>
        </div>
      )}
    </div>
  )
);

InlineResponse.displayName = 'InlineResponse';
export default InlineResponse;
