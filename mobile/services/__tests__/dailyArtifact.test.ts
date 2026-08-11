import api from '../api';
import {
  getDailyArtifactDetail,
  getDailyArtifact,
  recordDailyArtifactEvent,
  resolveDailyArtifactCompletionTarget,
} from '../dailyArtifact';

jest.mock('../api', () => ({
  get: jest.fn(),
  post: jest.fn(),
}));

describe('dailyArtifact service', () => {
  beforeEach(() => jest.clearAllMocks());

  it('loads and normalizes the current Daily Artifact', async () => {
    (api.get as jest.Mock).mockResolvedValue({
      data: {
        artifact_date: '2026-06-27',
        empty_state: false,
        state: { label: '今日最重要行动', tone: 'focused', summary: '先完成午间步行' },
        top_action: {
          id: 'a1',
          title: '午饭后步行 10 分钟',
          trajectory_context: {
            state_variable: 'waist_cm',
            horizon: 'upstream_90d',
            verification_window_days: 7,
            claim_boundary: '用于上游健康管理排序, 不替代医生诊断。',
          },
          target_state_variable: 'waist_cm',
          verification_signal: 'waist_cm',
          claim_boundary: '用于上游健康管理排序, 不替代医生诊断。',
          verify_by: {
            metrics: ['waist_cm'],
            window_days: 7,
            trajectory: { uncertainty_level: 'medium' },
          },
          runtime_context: { replan_reason: 'today_smart_rank' },
        },
        evidence: [
          { kind: 'why_now', label: 'Why now', summary: '餐后血糖窗口' },
          { kind: 'trajectory', label: 'Trajectory', summary: '近期活动不足' },
          { kind: 'verification', label: 'Verification', summary: '用步数验证' },
          { kind: 'extra', label: 'Extra', summary: '不应进入首屏' },
        ],
        confidence: 'medium',
        freshness: { status: 'fresh', sources: ['health_protocol'] },
        safety_boundary: '健康管理行动建议。',
      },
    });

    const artifact = await getDailyArtifact();

    expect(api.get).toHaveBeenCalledWith('/daily-artifact/me', {
      params: { followup_within_days: 7 },
    });
    expect(artifact.top_action?.title).toBe('午饭后步行 10 分钟');
    expect(artifact.top_action?.trajectory_context?.state_variable).toBe('waist_cm');
    expect(artifact.top_action?.target_state_variable).toBe('waist_cm');
    expect(artifact.top_action?.verification_signal).toBe('waist_cm');
    expect(artifact.top_action?.claim_boundary).toContain('不替代医生诊断');
    expect(artifact.top_action?.runtime_context?.replan_reason).toBe('today_smart_rank');
    expect(artifact.evidence).toHaveLength(3);
    expect(artifact.state.label).toBe('今日最重要行动');
  });

  it('loads a recoverable Daily Artifact detail by date and action id', async () => {
    (api.get as jest.Mock).mockResolvedValue({
      data: {
        artifact_date: '2026-06-29',
        empty_state: false,
        state: { label: '今日最重要行动', tone: 'focused', summary: '先恢复。' },
        top_action: {
          id: 'today-recovery',
          title: '今日训练:今天恢复/休息,暂停高强度;优先睡眠与轻活动',
        },
        evidence: [{ kind: 'why_now', label: 'Why now', summary: '恢复不足。' }],
        confidence: 'high',
        freshness: { status: 'fresh', sources: ['runtime'] },
        safety_boundary: '健康管理行动建议。',
      },
    });

    const artifact = await getDailyArtifactDetail({
      date: '2026-06-29',
      actionId: 'today-recovery',
    });

    expect(api.get).toHaveBeenCalledWith('/daily-artifact/me', {
      params: {
        artifact_date: '2026-06-29',
        followup_within_days: 7,
        top_action_id: 'today-recovery',
      },
    });
    expect(artifact?.artifact_date).toBe('2026-06-29');
    expect(artifact?.top_action?.id).toBe('today-recovery');
  });

  it('posts artifact events with snake_case payload', async () => {
    (api.post as jest.Mock).mockResolvedValue({
      data: {
        id: 9,
        event_type: 'skipped',
        skip_reason: 'too_tired',
        week_index: 2,
      },
    });

    const result = await recordDailyArtifactEvent({
      eventType: 'skipped',
      artifactDate: '2026-06-27',
      topActionId: 'a1',
      skipReason: 'too_tired',
      deliveredContext: { surface: 'home' },
    });

    expect(api.post).toHaveBeenCalledWith('/daily-artifact/me/events', {
      event_type: 'skipped',
      artifact_date: '2026-06-27',
      top_action_id: 'a1',
      skip_reason: 'too_tired',
      delivered_context: { surface: 'home' },
    });
    expect(result.week_index).toBe(2);
  });

  it('does not submit skipped events without a reason', async () => {
    await expect(recordDailyArtifactEvent({ eventType: 'skipped' }))
      .rejects.toThrow('skipReason is required');
    expect(api.post).not.toHaveBeenCalled();
  });

  it('resolves only completion sources that have a real write endpoint', () => {
    expect(resolveDailyArtifactCompletionTarget({
      id: 'protocol',
      title: '饮水',
      source: { object_type: 'health_protocol', object_id: 7, slot: '09:00' },
    })).toEqual({
      kind: 'agenda',
      source: { object_type: 'health_protocol', object_id: 7, slot: '09:00' },
    });
    expect(resolveDailyArtifactCompletionTarget({
      id: 'daily-plan',
      title: '餐后步行',
      source: { object_type: 'daily_plan_action', object_id: 'movement.walk_after_meal' },
    })).toEqual({ kind: 'daily_plan_action', actionId: 'movement.walk_after_meal' });
    expect(resolveDailyArtifactCompletionTarget({
      id: 'follow-up',
      title: '胃镜复查',
      source: { object_type: 'health_problem', object_id: 9 },
    })).toBeNull();
  });
});
