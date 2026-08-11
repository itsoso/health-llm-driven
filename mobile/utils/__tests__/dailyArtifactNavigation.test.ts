import type { DailyArtifact, DailyArtifactTopAction } from '../../services/dailyArtifact';
import {
  buildDailyArtifactAskRoute,
  buildDailyArtifactBasisChatRoute,
  buildDailyArtifactBasisRoute,
  buildDailyArtifactExecuteRoute,
  inferDailyArtifactMovementTarget,
  normalizeHealthActionRoute,
  routeForNutritionActionText,
} from '../dailyArtifactNavigation';

function action(overrides: Partial<DailyArtifactTopAction> = {}): DailyArtifactTopAction {
  return {
    id: 'today-training',
    title: '今日训练:今天恢复/休息,暂停高强度;优先睡眠与轻活动',
    why_now: '近期恢复不足。',
    do_now: '先睡眠和轻活动。',
    source: null,
    actions: {
      ask_reva: { target: '/voice-chat?intent=daily_artifact' },
    },
    ...overrides,
  };
}

function artifact(overrides: Partial<DailyArtifact> = {}): DailyArtifact {
  return {
    artifact_date: '2026-06-29',
    generated_by: 'daily_artifact',
    source: { kind: 'health_os' },
    empty_state: false,
    state: { label: '今日最重要行动', tone: 'focused', summary: '恢复优先。' },
    top_action: action(),
    evidence: [{ kind: 'verification', label: 'Verification', summary: '后续用睡眠和腰围验证。' }],
    confidence: 'medium',
    freshness: { status: 'fresh', sources: ['twin'] },
    safety_boundary: '用于健康管理,不替代医生诊断。',
    ...overrides,
  };
}

describe('dailyArtifactNavigation', () => {
  it('routes the ask action into Aheng chat even when backend still sends the legacy voice target', () => {
    const route = buildDailyArtifactAskRoute(artifact());

    expect(route.pathname).toBe('/(tabs)/chat');
    expect(route.params.prompt).toContain('恢复/休息');
    expect(route.params.prompt).not.toContain('今日训练:今天');
    expect(route.params.badge).toBe('今日最重要行动');
    expect(JSON.parse(route.params.context).top_action.title).toContain('恢复/休息');
  });

  it('routes decision basis explanation into a local detail page with evidence context', () => {
    const route = buildDailyArtifactBasisRoute(artifact({
      evidence: [
        { kind: 'why_now', label: 'Why now', summary: '恢复不足,先降低训练负荷。' },
        { kind: 'verification', label: 'Verification', summary: '后续用睡眠和腰围验证。' },
      ],
    }));

    expect(route.pathname).toBe('/daily-artifact/[date]');
    expect(route.params.date).toBe('2026-06-29');
    expect(route.params.actionId).toBe('today-training');
    const payload = JSON.parse(route.params.artifact);
    expect(payload.intent).toBe('explain_basis');
    expect(payload.evidence).toHaveLength(2);
    expect(payload.top_action.title).toContain('恢复/休息');
    expect(payload.top_action.title).not.toContain('今日训练:今天');
  });

  it('keeps a dedicated Aheng route for continuing the basis discussion from the detail page', () => {
    const route = buildDailyArtifactBasisChatRoute(artifact());

    expect(route.pathname).toBe('/(tabs)/chat');
    expect(route.params.prompt).toContain('决策依据');
    expect(route.params.prompt).toContain('恢复/休息');
    expect(route.params.badge).toBe('决策依据');
    expect(JSON.parse(route.params.context).intent).toBe('explain_basis');
  });

  it('sends recovery/rest training actions to the movement plan instead of a blank timeline page', () => {
    expect(inferDailyArtifactMovementTarget(action())).toBe('recovery');
    expect(buildDailyArtifactExecuteRoute(artifact(), action())).toBe('/movement-plan');
  });

  it('opens guided strength tasks with a completion ref when a concrete training action is executable', () => {
    const training = action({
      title: '今天做 3 组俯卧撑训练',
      do_now: '按组完成。',
      source: { object_type: 'health_protocol', object_id: 7, slot: '21:00' },
    });

    expect(inferDailyArtifactMovementTarget(training)).toBe('strength');
    expect(buildDailyArtifactExecuteRoute(artifact({ top_action: training }), training)).toBe(
      '/guided-task?domain=strength&completeType=health_protocol&completeId=7&slot=21%3A00',
    );
  });

  it('routes diet record actions to the diet capture screen instead of the diet plan', () => {
    const breakfastLog = action({
      id: 'breakfast-log',
      title: '记录早餐',
      do_now: '把今天早餐拍照或文字记录下来。',
      source: null,
    });

    expect(routeForNutritionActionText('记录早餐')).toBe('/diet');
    expect(routeForNutritionActionText('记录今天早餐')).toBe('/diet');
    expect(buildDailyArtifactExecuteRoute(artifact({ top_action: breakfastLog }), breakfastLog)).toBe('/diet');
  });

  it('routes photo meal actions directly into camera capture', () => {
    const photoLog = action({
      id: 'photo-meal-log',
      title: '拍照记餐',
      do_now: '打开相机拍一下今天午餐。',
      source: null,
    });

    expect(routeForNutritionActionText('拍照记餐')).toBe('/diet?capture=photo&return_to=chat');
    expect(routeForNutritionActionText('把早餐拍照记录下来')).toBe('/diet?capture=photo&return_to=chat');
    expect(buildDailyArtifactExecuteRoute(artifact({ top_action: photoLog }), photoLog)).toBe('/diet?capture=photo&return_to=chat');
  });

  it('upgrades generic diet deep links to camera capture for photo meal actions', () => {
    const photoLog = action({
      id: 'photo-meal-log',
      title: '拍照记餐',
      do_now: '打开相机拍一下今天午餐。',
      source: null,
      actions: {
        execute: { route: '/diet' },
      },
    } as any);

    expect(buildDailyArtifactExecuteRoute(artifact({ top_action: photoLog }), photoLog)).toBe('/diet?capture=photo&return_to=chat');
  });

  it('upgrades raw generic diet routes when the surrounding action text means photo meal capture', () => {
    expect(normalizeHealthActionRoute('/diet', '拍照记餐 打开相机拍一下今天午餐')).toBe('/diet?capture=photo&return_to=chat');
    expect(normalizeHealthActionRoute('/diet', '记录午餐')).toBe('/diet');
    expect(normalizeHealthActionRoute('/diet?capture=photo', '拍照记餐')).toBe('/diet?capture=photo&return_to=chat');
  });

  it('keeps nutrition advice actions on the diet plan screen', () => {
    const nutritionPlan = action({
      id: 'protein-breakfast',
      title: '早餐补足 30g 蛋白',
      do_now: '查看今天这一餐怎么吃。',
      source: null,
    });

    expect(routeForNutritionActionText('早餐补足 30g 蛋白')).toBe('/diet-plan');
    expect(buildDailyArtifactExecuteRoute(artifact({ top_action: nutritionPlan }), nutritionPlan)).toBe('/diet-plan');
  });

  it('opens the medical exam workflow for a due follow-up action', () => {
    const followUp = action({
      id: 'gastric-follow-up',
      type: 'checkup',
      title: '复查:胃溃疡(Hp 阴性,胃窦后壁)',
      do_now: '安排检查或确认已完成。',
      source: { object_type: 'health_problem', object_id: 9 },
    });

    expect(buildDailyArtifactExecuteRoute(artifact({ top_action: followUp }), followUp)).toBe('/medical-exams');
    expect(buildDailyArtifactExecuteRoute(
      artifact({ top_action: followUp }),
      followUp,
      { nowDeepLink: '/hydration' },
    )).toBe('/medical-exams');
  });

  it('falls back to Aheng chat, not timeline, for unsupported source-backed actions', () => {
    const unsupported = action({
      title: '核对一条健康建议',
      why_now: '需要确认上下文。',
      do_now: '查看建议详情。',
      source: { object_type: 'health_problem', object_id: 9 },
    });
    const route = buildDailyArtifactExecuteRoute(artifact({ top_action: unsupported }), unsupported);

    expect(route).not.toBe('/timeline');
    expect(typeof route).toBe('object');
    if (typeof route !== 'string') {
      expect(route.pathname).toBe('/(tabs)/chat');
      expect(route.params.prompt).toContain('拆成现在可执行的步骤');
    }
  });
});
