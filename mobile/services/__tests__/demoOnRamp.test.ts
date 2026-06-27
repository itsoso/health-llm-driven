import {
  buildDemoOnRampRuntime,
  getDemoOnRampChatRoute,
} from '../demoOnRamp';

describe('demo on-ramp runtime', () => {
  const NOW = new Date('2026-06-27T08:00:00+08:00').getTime();

  it('builds a local demo runtime that cannot write to the real health profile', () => {
    const runtime = buildDemoOnRampRuntime(NOW);

    expect(runtime.mode).toBe('demo');
    expect(runtime.isolated).toBe(true);
    expect(runtime.sourceLabel).toContain('示例');
    expect(runtime.sourceLabel).toContain('不写入');
    expect(runtime.dailyArtifact.tracking.artifactId).toContain('demo');
    expect(runtime.dailyArtifact.actions.canComplete).toBe(false);
    expect(runtime.dailyArtifact.actions.canSkip).toBe(false);
    expect(runtime.dailyArtifact.topAction?.completeRef).toBeNull();
    expect(runtime.milestones.map(item => item.key)).toEqual([
      'safety_brain',
      'evidence_card',
      'top_action',
    ]);
  });

  it('opens chat with explicit demo context and a fresh conversation', () => {
    const route = getDemoOnRampChatRoute(buildDemoOnRampRuntime(NOW));

    expect(route.pathname).toBe('/(tabs)/chat');
    expect(route.params.badge).toBe('示例体验');
    expect(route.params.newChat).toBe('1');
    expect(route.params.prompt).toContain('示例数据');

    const context = JSON.parse(route.params.context);
    expect(context.demo).toBe(true);
    expect(context.write_policy).toBe('never_persist_demo_data');
    expect(context.runtime.daily_artifact.top_action.title).toBe('午餐后步行 10 分钟');
  });
});
