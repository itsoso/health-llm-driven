'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Users, Loader2, Check } from 'lucide-react';
import {
  getConnectionStatus,
  submitConnectionCheckin,
} from '@/services/api/chronicHealth';

// UCLA-3 三题,各 1-3 分(1=几乎不 / 2=有时 / 3=经常),总分 3-9。
const UCLA_QUESTIONS = [
  '你多久会感到缺少陪伴?',
  '你多久会感到被冷落?',
  '你多久会感到与他人疏离、孤立?',
];
const UCLA_OPTIONS = [
  { value: 1, label: '几乎不' },
  { value: 2, label: '有时' },
  { value: 3, label: '经常' },
];

export default function ConnectionSection() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['connection-status'],
    queryFn: getConnectionStatus,
  });

  const [answers, setAnswers] = useState<(number | null)[]>([null, null, null]);
  const [hasConfidant, setHasConfidant] = useState<boolean | null>(null);
  const [inStableGroup, setInStableGroup] = useState<boolean | null>(null);

  const mutation = useMutation({
    mutationFn: submitConnectionCheckin,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connection-status'] });
      setAnswers([null, null, null]);
      setHasConfidant(null);
      setInStableGroup(null);
    },
  });

  const allAnswered =
    answers.every((a) => a !== null) &&
    hasConfidant !== null &&
    inStableGroup !== null;

  const handleSubmit = () => {
    if (!allAnswered) return;
    const uclaScore = answers.reduce<number>((sum, a) => sum + (a ?? 0), 0);
    mutation.mutate({
      ucla_score: uclaScore,
      has_confidant: hasConfidant as boolean,
      in_stable_group: inStableGroup as boolean,
    });
  };

  return (
    <section className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <header className="flex items-center gap-2 mb-1">
        <Users className="w-5 h-5 text-rose-500" />
        <h2 className="text-lg font-semibold text-gray-800">社会连接自评</h2>
      </header>
      <p className="text-sm text-gray-500 mb-4">
        关系质量是长期健康最强的单一预测因子之一。这是一份简短自评,非诊断。
      </p>

      {/* 当前状态 */}
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400 py-4 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" /> 加载中…
        </div>
      ) : isError ? (
        <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-4">
          状态加载失败,你仍可在下方提交自评。
        </p>
      ) : data ? (
        <div className="rounded-xl bg-rose-50/60 border border-rose-100 px-4 py-3 mb-5 text-sm">
          <p className="text-gray-700">{data.interpretation}</p>
          {data.has_checkin && (
            <p className="text-xs text-gray-400 mt-1.5">
              上次自评:{data.last_date}
              {data.days_since != null && ` · ${data.days_since} 天前`}
              {data.ucla_score != null && ` · UCLA-3 ${data.ucla_score}/9`}
              {data.due && ' · 已到期,建议重测'}
            </p>
          )}
        </div>
      ) : null}

      {/* 自评表单 */}
      <div className="space-y-4">
        {UCLA_QUESTIONS.map((q, qi) => (
          <div key={qi}>
            <p className="text-sm text-gray-700 mb-2">
              {qi + 1}. {q}
            </p>
            <div className="flex gap-2">
              {UCLA_OPTIONS.map((opt) => {
                const selected = answers[qi] === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() =>
                      setAnswers((prev) => {
                        const next = [...prev];
                        next[qi] = opt.value;
                        return next;
                      })
                    }
                    className={`flex-1 rounded-lg border px-3 py-2 text-sm transition-colors ${
                      selected
                        ? 'border-rose-400 bg-rose-50 text-rose-700 font-medium'
                        : 'border-gray-200 text-gray-500 hover:border-rose-200'
                    }`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>
        ))}

        <BooleanRow
          label="你是否有一位可以倾诉心事的知心人?"
          value={hasConfidant}
          onChange={setHasConfidant}
        />
        <BooleanRow
          label="你是否有一个稳定参与的群体(家庭 / 朋友 / 社群)?"
          value={inStableGroup}
          onChange={setInStableGroup}
        />
      </div>

      <button
        type="button"
        onClick={handleSubmit}
        disabled={!allAnswered || mutation.isPending}
        className="mt-5 w-full inline-flex items-center justify-center gap-2 rounded-xl bg-rose-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-rose-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {mutation.isPending ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Check className="w-4 h-4" />
        )}
        提交自评
      </button>
      {mutation.isError && (
        <p className="mt-2 text-sm text-red-600">提交失败,请稍后重试。</p>
      )}
      {mutation.isSuccess && (
        <p className="mt-2 text-sm text-emerald-600">已提交,解读已更新。</p>
      )}
    </section>
  );
}

function BooleanRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean | null;
  onChange: (v: boolean) => void;
}) {
  return (
    <div>
      <p className="text-sm text-gray-700 mb-2">{label}</p>
      <div className="flex gap-2">
        {[
          { v: true, t: '是' },
          { v: false, t: '否' },
        ].map((opt) => {
          const selected = value === opt.v;
          return (
            <button
              key={opt.t}
              type="button"
              onClick={() => onChange(opt.v)}
              className={`flex-1 rounded-lg border px-3 py-2 text-sm transition-colors ${
                selected
                  ? 'border-rose-400 bg-rose-50 text-rose-700 font-medium'
                  : 'border-gray-200 text-gray-500 hover:border-rose-200'
              }`}
            >
              {opt.t}
            </button>
          );
        })}
      </div>
    </div>
  );
}
