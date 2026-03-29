'use client';

import { Star, Lightbulb, AlertTriangle, Trash2 } from 'lucide-react';
import { WeeklyPlan } from './types';

interface PlanSummaryProps {
  plan: WeeklyPlan;
  showFeedback: boolean;
  feedbackScore: number;
  feedbackPending: boolean;
  deletePending: boolean;
  onToggleFeedback: () => void;
  onSetFeedbackScore: (score: number) => void;
  onSubmitFeedback: () => void;
  onDelete: () => void;
}

export function PlanSummary({
  plan,
  showFeedback,
  feedbackScore,
  feedbackPending,
  onToggleFeedback,
  onSetFeedbackScore,
  onSubmitFeedback,
  onDelete,
}: PlanSummaryProps) {
  return (
    <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl p-5 mt-6">
      {/* Focus Areas */}
      {plan.focus_areas.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {plan.focus_areas.map((area, idx) => (
            <span key={idx} className="text-xs bg-white/70 text-blue-700 px-2 py-1 rounded-full">
              {area}
            </span>
          ))}
        </div>
      )}

      {plan.weekly_summary && (
        <p className="text-sm text-gray-600 leading-relaxed">{plan.weekly_summary}</p>
      )}

      {/* AI Insights */}
      {plan.ai_insights && plan.ai_insights.length > 0 && (
        <div className="mt-3 space-y-1.5">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-700">
            <Lightbulb className="w-3.5 h-3.5" />
            <span>AI 数据洞察</span>
          </div>
          {plan.ai_insights.map((insight, idx) => (
            <div key={idx} className="text-xs text-gray-600 bg-white/60 rounded-lg px-3 py-2 leading-relaxed">
              {insight}
            </div>
          ))}
        </div>
      )}

      {/* AI Risks */}
      {plan.ai_risks && plan.ai_risks.length > 0 && (
        <div className="mt-3 space-y-1.5">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-red-600">
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>风险提示</span>
          </div>
          {plan.ai_risks.map((risk, idx) => (
            <div key={idx} className="text-xs text-red-700 bg-red-50/60 rounded-lg px-3 py-2 leading-relaxed">
              {risk}
            </div>
          ))}
        </div>
      )}

      {/* Feedback & Delete */}
      <div className="flex items-center gap-3 mt-4 pt-3 border-t border-blue-100">
        {plan.user_feedback ? (
          <div className="flex items-center gap-1 text-sm text-gray-500">
            <span>评分:</span>
            {[1, 2, 3, 4, 5].map(s => (
              <Star key={s} className={`w-4 h-4 ${s <= plan.user_feedback! ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300'}`} />
            ))}
          </div>
        ) : (
          <button
            onClick={onToggleFeedback}
            className="text-sm text-blue-600 hover:text-blue-700"
          >
            评价本周计划
          </button>
        )}
        <button
          onClick={onDelete}
          className="ml-auto text-gray-400 hover:text-red-500 transition-colors"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {/* Feedback Form */}
      {showFeedback && !plan.user_feedback && (
        <div className="flex items-center gap-3 mt-3 pt-3 border-t border-blue-100">
          <span className="text-sm text-gray-600">评分:</span>
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map(s => (
              <button key={s} onClick={() => onSetFeedbackScore(s)}>
                <Star className={`w-6 h-6 transition-colors ${s <= feedbackScore ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300 hover:text-yellow-300'}`} />
              </button>
            ))}
          </div>
          {feedbackScore > 0 && (
            <button
              onClick={onSubmitFeedback}
              disabled={feedbackPending}
              className="text-sm px-3 py-1 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              提交
            </button>
          )}
        </div>
      )}
    </div>
  );
}
