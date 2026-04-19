'use client';

import { useCallback, useEffect, useState } from 'react';
import { useDashboardData } from '@/hooks/useDashboardData';
import HeroCard from '@/components/assistant/HeroCard';
import CollapsibleCard from '@/components/assistant/CollapsibleCard';
import ConsultationsCard from '@/components/assistant/ConsultationsCard';
import AlertsBanner from '@/components/assistant/AlertsBanner';
import SafetyPanel from '@/components/assistant/SafetyPanel';
import SpecialistsPanel from '@/components/assistant/SpecialistsPanel';
import ActionCardPanel from '@/components/assistant/ActionCardPanel';
import dynamic from 'next/dynamic';

const DndDashboard = dynamic(() => import('@/components/assistant/DndDashboard'), { ssr: false });

import DataGrid from '@/components/assistant/DataGrid';
import ActivityCard from '@/components/assistant/ActivityCard';
import SupplementCheckin from '@/components/assistant/SupplementCheckin';
import TrendsCard from '@/components/assistant/TrendsCard';
import InlineResponse from '@/components/assistant/InlineResponse';
import ExerciseCard from '@/components/assistant/ExerciseCard';
import SupplementGuideCard from '@/components/assistant/SupplementGuideCard';
import StrengthCard from '@/components/assistant/StrengthCard';
import WorkoutCard from '@/components/assistant/WorkoutCard';

const QUICK_ASKS = [
  { text: '帮我分析一下最近的睡眠质量', label: '睡眠分析' },
  { text: '根据我的身体数据，今天适合做什么运动？', label: '运动建议' },
  { text: '帮我记录一下刚才吃的饭', label: '记录饮食' },
  { text: '查看今日 AI 洞察和健康分析详情', label: 'AI 洞察' },
  { text: '分析我最近的HRV趋势，给出恢复建议', label: '趋势报告' },
];

export const DASHBOARD_CARD_LABELS: Record<string, string> = {
  hero: '今日总览',
  safety: '安全守护',
  consultations: '健康咨询',
  action_cards: '行动卡片',
  specialists: '专家协作',
  alerts: '提醒横幅',
  data_grid: '健康数据',
  strength: '力量训练',
  workout_supplement: '运动与补剂',
  supplement_guide: '补剂指南',
  activity: '活动摘要',
  exercise: '今日练习',
  trends: '趋势分析',
  quick_asks: '快捷提问',
};

interface WelcomeDashboardProps {
  user: any;
  dashboard: ReturnType<typeof useDashboardData>;
  suppChecked: number;
  suppTotal: number;
  handleRefresh: () => Promise<void>;
  handleWaterRecord: (amount: number) => void;
  handleSend: (text?: string) => void;
  visibleDashboardCardIds: string[];
  dashboardEditMode: boolean;
  renderDashboardCardOverride?: (cardId: string) => React.ReactNode;
  onDragEnd: (oldIndex: number, newIndex: number) => void;
  onHideCard: (cardId: string) => void;
  welcomeBottomPaddingClass: string;
  layoutSaveError: string | null;
  inlineResponse: {question: string; answer: string; loading: boolean} | null;
  inlineResponseRef: React.Ref<HTMLDivElement>;
  onInlineClose: () => void;
}

export default function WelcomeDashboard({
  user,
  dashboard,
  suppChecked,
  suppTotal,
  handleRefresh,
  handleWaterRecord,
  handleSend,
  visibleDashboardCardIds,
  dashboardEditMode,
  onDragEnd,
  onHideCard,
  welcomeBottomPaddingClass,
  layoutSaveError,
  inlineResponse,
  inlineResponseRef,
  onInlineClose,
}: WelcomeDashboardProps) {

  // 折叠态持久化到 localStorage（与云端 layout 分离，纯本地 UI 状态）
  const COLLAPSE_STORAGE_KEY = 'assistant_dashboard_collapsed_v1';
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(() => new Set());
  const [collapseLoaded, setCollapseLoaded] = useState(false);

  useEffect(() => {
    try {
      const raw = typeof window !== 'undefined' ? window.localStorage.getItem(COLLAPSE_STORAGE_KEY) : null;
      if (raw) {
        const arr = JSON.parse(raw);
        if (Array.isArray(arr)) setCollapsedIds(new Set(arr.filter((x: unknown) => typeof x === 'string')));
      }
    } catch { /* ignore */ }
    setCollapseLoaded(true);
  }, []);

  useEffect(() => {
    if (!collapseLoaded) return;
    try {
      window.localStorage.setItem(COLLAPSE_STORAGE_KEY, JSON.stringify(Array.from(collapsedIds)));
    } catch { /* ignore */ }
  }, [collapsedIds, collapseLoaded]);

  const handleToggleCollapse = useCallback((cardId: string, next: boolean) => {
    setCollapsedIds((prev) => {
      const copy = new Set(prev);
      if (next) copy.add(cardId); else copy.delete(cardId);
      return copy;
    });
  }, []);

  const renderDashboardCard = useCallback((cardId: string) => {
    switch (cardId) {
      case 'hero':
        return (
          <HeroCard
            user={user}
            healthScore={dashboard.healthScore}
            todayGarmin={dashboard.todayGarmin}
            waterToday={dashboard.waterToday}
            suppChecked={suppChecked}
            suppTotal={suppTotal}
            weatherData={dashboard.weatherData}
            airData={dashboard.airData}
            onRefresh={handleRefresh}
          />
        );
      case 'safety':
        return <SafetyPanel />;
      case 'consultations':
        return <ConsultationsCard />;
      case 'action_cards':
        return <ActionCardPanel />;
      case 'specialists':
        return <SpecialistsPanel />;
      case 'alerts':
        return <AlertsBanner waterToday={dashboard.waterToday} todayGarmin={dashboard.todayGarmin} onWaterRecord={handleWaterRecord} onAskAI={(text) => handleSend(text)} />;
      case 'data_grid':
        return <DataGrid todayGarmin={dashboard.todayGarmin} dietToday={dashboard.dietToday} bpLatest={dashboard.bpLatest} rhinitisToday={dashboard.rhinitisToday} weightStats={dashboard.weightStats} medToday={dashboard.medToday} />;
      case 'strength':
        return (
          <div className="grid grid-cols-2 gap-3">
            <StrengthCard exerciseType="俯卧撑" icon="💪" dailyTarget={100} color="#3b82f6"
              colorLight="bg-blue-50" colorText="text-blue-600" colorBorder="border-blue-200"
              colorBar="bg-blue-500" colorBarLight="bg-blue-200" />
            <StrengthCard exerciseType="深蹲" icon="🦵" dailyTarget={100} color="#8b5cf6"
              colorLight="bg-violet-50" colorText="text-violet-600" colorBorder="border-violet-200"
              colorBar="bg-violet-500" colorBarLight="bg-violet-200" />
          </div>
        );
      case 'workout_supplement':
        return (
          <div className="grid grid-cols-2 gap-3">
            <WorkoutCard todayGarmin={dashboard.todayGarmin} workoutRecent={dashboard.workoutRecent} />
            <SupplementCheckin supplementStatus={dashboard.supplementStatus} onStatusChange={dashboard.setSupplementStatus} />
          </div>
        );
      case 'supplement_guide':
        return <SupplementGuideCard />;
      case 'activity':
        return <ActivityCard todayGarmin={dashboard.todayGarmin} workoutRecent={dashboard.workoutRecent} medToday={dashboard.medToday} />;
      case 'exercise':
        if (dashboard.exerciseToday.length === 0) {
          if (!dashboardEditMode) return null;
          return (
            <div className="rounded-2xl border border-dashed border-gray-300 bg-white px-4 py-5 text-sm text-gray-500">
              今日练习卡片当前无内容。你仍然可以调整它在首页中的位置，等有训练数据后会自动显示。
            </div>
          );
        }
        return <ExerciseCard exerciseToday={dashboard.exerciseToday} />;
      case 'trends':
        return <TrendsCard garminHistory={dashboard.garminHistory} />;
      case 'quick_asks':
        return (
          <div className="flex flex-wrap gap-1.5 rounded-2xl bg-white px-3 py-3">
            {QUICK_ASKS.map(q => (
              <button key={q.label} onClick={() => handleSend(q.text)}
                className="px-2.5 py-1 rounded-lg border border-gray-200 bg-white text-[11px] text-gray-600 hover:border-emerald-300 hover:text-emerald-700 hover:bg-emerald-50 active:scale-[0.97] transition-all">
                {q.label}
              </button>
            ))}
          </div>
        );
      default:
        return null;
    }
  }, [user, dashboard, suppChecked, suppTotal, handleRefresh, handleWaterRecord, handleSend, dashboardEditMode]);

  return (
    <div className={`space-y-3 overflow-x-hidden ${welcomeBottomPaddingClass}`}>
      {layoutSaveError && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
          {layoutSaveError}
        </div>
      )}

      {dashboardEditMode ? (
        <DndDashboard
          cardIds={visibleDashboardCardIds}
          renderCard={renderDashboardCard}
          onDragEnd={onDragEnd}
          onHideCard={onHideCard}
        />
      ) : (
        <>
          {visibleDashboardCardIds.map((cardId) => {
            const content = renderDashboardCard(cardId);
            if (!content) return null;
            // hero 卡片保持常展开（是整个首页的主视觉锚点）
            if (cardId === 'hero') return <div key={cardId}>{content}</div>;
            const label = DASHBOARD_CARD_LABELS[cardId] || cardId;
            return (
              <CollapsibleCard
                key={cardId}
                cardId={cardId}
                label={label}
                collapsed={collapsedIds.has(cardId)}
                onToggle={handleToggleCollapse}
              >
                {content}
              </CollapsibleCard>
            );
          })}
        </>
      )}

      {/* Inline AI Response */}
      {inlineResponse && (
        <InlineResponse ref={inlineResponseRef} question={inlineResponse.question} answer={inlineResponse.answer} loading={inlineResponse.loading} onClose={onInlineClose} />
      )}
    </div>
  );
}
