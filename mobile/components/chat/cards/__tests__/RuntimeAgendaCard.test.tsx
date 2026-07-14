/**
 * RuntimeAgendaCard 隔离测试 — 走 registry renderCard 路径 (与后端下发同一条链路).
 *
 * 目标: text()/numberText()/metrics()/days() 空值防御在真实渲染路径上被验证,
 * 而不是只被全量 descriptor 的 registry 测试间接覆盖。
 */
import { fireEvent, render } from '@testing-library/react-native';
import { renderCard } from '../registry';

function renderRuntimeAgendaCard(data: unknown) {
  const element = renderCard({ type: 'runtime_agenda', data });
  expect(element).not.toBeNull();
  return render(element!);
}

describe('RuntimeAgendaCard via registry renderCard', () => {
  it('renders minimal card with empty data {} (no crash)', () => {
    const { getByText, queryByText } = renderRuntimeAgendaCard({});

    // horizon 兜底 7 天 + 固定骨架
    expect(getByText('今天先做')).toBeTruthy();
    expect(getByText('今天行动')).toBeTruthy();
    // formatHealthActionTitle 会剥掉兜底文案的前导"今日"
    expect(getByText('暂无明确行动')).toBeTruthy();
    // 安全边界兜底文案
    expect(getByText('这是健康管理建议,不替代医生诊断。')).toBeTruthy();
    // 可选分区全部不出现
    expect(queryByText('为什么现在')).toBeNull();
    expect(queryByText('验证信号')).toBeNull();
    expect(queryByText('未来节奏')).toBeNull();
  });

  it('renders when every optional field group is null/undefined (no crash)', () => {
    const { getByText, queryByText } = renderRuntimeAgendaCard({
      generated_by: null,
      horizon_days: null,
      start: null,
      end: undefined,
      safety_boundary: null,
      next_action: {
        title: null,
        kind: undefined,
        time_window: null,
        priority_tier: null,
        current_state_summary: null,
        replan_reason: null,
        verification_metrics: null,
        verification_window_days: null,
      },
      days: [null, undefined],
    });

    expect(getByText('今天先做')).toBeTruthy();
    expect(getByText('暂无明确行动')).toBeTruthy();
    expect(getByText('这是健康管理建议,不替代医生诊断。')).toBeTruthy();
    expect(queryByText('为什么现在')).toBeNull();
    expect(queryByText('验证信号')).toBeNull();
    // days 里全是 null/undefined → 分区整体不渲染
    expect(queryByText('未来节奏')).toBeNull();
  });

  it('renders gracefully with malformed types (metrics as string, days as object)', () => {
    const { getByText, queryByText } = renderRuntimeAgendaCard({
      horizon_days: { value: 7 },
      next_action: {
        title: 42,
        kind: 123,
        time_window: ['evening'],
        priority_tier: {},
        verification_metrics: 'hrv,waist_cm',
        verification_window_days: { d: 7 },
      },
      days: { '0': { date: '2026-06-28' } },
      safety_boundary: 12345,
    });

    // horizon 非数字对象 → 兜底 7
    expect(getByText('今天先做')).toBeTruthy();
    // number title 被 text() 归一成字符串
    expect(getByText('42')).toBeTruthy();
    // boundary number 被 text() 归一成字符串
    expect(getByText('12345')).toBeTruthy();
    // metrics 非数组 → 分区不渲染
    expect(queryByText('验证信号')).toBeNull();
    // days 非数组 → 分区不渲染
    expect(queryByText('未来节奏')).toBeNull();
  });

  it('survives non-object next_action and junk day entries (no crash)', () => {
    const { getByText, queryByText } = renderRuntimeAgendaCard({
      next_action: 'junk',
      days: ['junk'],
    });

    expect(getByText('今天先做')).toBeTruthy();
    // 字符串 next_action 上取不到 title → 兜底文案
    expect(getByText('暂无明确行动')).toBeTruthy();
    // 今天模式不展示预测列表，脏数据也不会撑高卡片。
    expect(queryByText('今天')).toBeNull();
    expect(queryByText('待运行时重排')).toBeNull();
  });

  it('keeps the future cadence collapsed until the user asks for it', () => {
    const { getByText, queryByText, getByLabelText } = renderRuntimeAgendaCard({
      presentation_mode: 'horizon',
      generated_by: 'rolling_health_runtime_v1',
      horizon_days: 7,
      start: '2026-06-28',
      end: '2026-07-04',
      safety_boundary: '这是健康管理行动建议, 不替代医生诊断。',
      next_action: {
        title: '晚餐后步行 15 分钟',
        kind: 'movement',
        time_window: 'evening',
        priority_tier: 'P1',
        current_state_summary: '晚餐后是今天最短的代谢干预窗口。',
        replan_reason: 'today_smart_rank',
        verification_metrics: ['post_meal_walk_completed', 'waist_cm', 'hrv'],
        verification_window_days: 7,
      },
      days: [
        { date: '2026-06-28', next_action_title: '晚餐后步行 15 分钟', items_count: 3 },
        { date: '2026-06-29', next_action_title: null, items_count: 0 },
      ],
    });

    expect(getByText('本周验证节奏')).toBeTruthy();
    expect(getByText('晚餐后步行 15 分钟')).toBeTruthy();
    expect(getByText('晚餐后是今天最短的代谢干预窗口。')).toBeTruthy();
    // signal pills: kind / time_window / priority / 验证窗口
    expect(getByText('运动')).toBeTruthy();
    expect(getByText('晚间')).toBeTruthy();
    expect(getByText('重要')).toBeTruthy();
    expect(getByText('7天后复盘')).toBeTruthy();
    // 周期只在用户主动请求时按需展开；重排原因仍保留。
    expect(getByText('按需展开')).toBeTruthy();
    expect(getByText('基于今日状态重排')).toBeTruthy();
    // 验证信号 labels
    expect(getByText('验证信号')).toBeTruthy();
    expect(getByText('餐后步行完成')).toBeTruthy();
    expect(getByText('腰围')).toBeTruthy();
    expect(getByText('HRV')).toBeTruthy();
    // 未来节奏默认折叠，避免把尚未锁定的 7 天任务全部压到首屏。
    expect(queryByText('未来节奏')).toBeNull();
    expect(queryByText('明天')).toBeNull();
    fireEvent.press(getByLabelText('展开后续6天'));
    expect(getByText('未来节奏')).toBeTruthy();
    expect(getByText('明天')).toBeTruthy();
    // 只展示未来日期，不重复今天的行动。
    expect(queryByText('今天')).toBeNull();
    expect(getByText('待运行时重排')).toBeTruthy();
    expect(getByText('当天根据状态确认')).toBeTruthy();
    // boundary 用后端下发的文案
    expect(getByText('这是健康管理行动建议, 不替代医生诊断。')).toBeTruthy();
  });

  it('maps domain-key kind (training) to Chinese instead of leaking the raw English token', () => {
    const { getByText, queryByText } = renderRuntimeAgendaCard({
      next_action: {
        title: '力量训练 3 组',
        kind: 'training',
      },
    });

    // kind=training 应显示"训练",而不是原始英文 "training"
    expect(getByText('训练')).toBeTruthy();
    expect(queryByText('training')).toBeNull();
  });

  it('renders unknown kind as-is (underscores→spaces, no crash, no mid-word truncation)', () => {
    const { getByText } = renderRuntimeAgendaCard({
      next_action: {
        title: '未知领域行动',
        kind: 'brand_new_domain',
      },
    });

    // 未知 key 兜底: 仅把下划线换成空格, 不截断
    expect(getByText('brand new domain')).toBeTruthy();
  });
});
