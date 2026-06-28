import api from '../api';
import {
  getDailyArtifact,
  recordDailyArtifactEvent,
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
    expect(artifact.top_action?.runtime_context?.replan_reason).toBe('today_smart_rank');
    expect(artifact.evidence).toHaveLength(3);
    expect(artifact.state.label).toBe('今日最重要行动');
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
});
