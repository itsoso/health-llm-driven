import React from 'react';
import { render } from '@testing-library/react-native';
import { MedicationListCardView } from '../MedicationListCard';
import { renderCard, CARD_MAP } from '../registry';
import { extractRevaUiBlocks } from '../../../../utils/revaUiBlocks';
import { buildClientCapsHeader } from '../../../../services/clientCaps';

// 契约 fixture = 后端 medication_list 的 descriptor.data(字段逐一对齐)。
const data = {
  medications: [
    {
      name: '沃克（伏诺拉生）',
      dosage: '20mg',
      frequency: '每日2次',
      timing_label: '餐前',
      category: '胃药',
      purpose: '胃窦溃疡',
      start_date: '2026-07-01',
    },
    {
      name: '瑞巴派特',
      dosage: '100mg',
      frequency: '每日3次',
      timing_label: '餐后',
      category: '胃药',
      purpose: '黏膜保护',
      start_date: '2026-07-01',
    },
  ],
  total: 2,
  safety_alert_count: 1,
};

describe('MedicationListCardView', () => {
  it('renders header count, drug names, dosage/frequency/timing meta, category/purpose tags', () => {
    const { getByText } = render(<MedicationListCardView data={data} />);
    expect(getByText('在用药物')).toBeTruthy();
    expect(getByText('共 2 条 · 1 条用药安全提示')).toBeTruthy();
    expect(getByText('沃克（伏诺拉生）')).toBeTruthy();
    expect(getByText('瑞巴派特')).toBeTruthy();
    expect(getByText('20mg · 每日2次 · 餐前')).toBeTruthy();
    expect(getByText('100mg · 每日3次 · 餐后')).toBeTruthy();
    expect(getByText('胃窦溃疡')).toBeTruthy();
  });

  it('surfaces the safety signal at CARD level, never attributed to a single drug', () => {
    // 契约承重墙:后端 safety_alerts 是**用户级**的(服务端按整个方案跑 PGx/DDI/DSI,
    // 同一份挂到每个条目)→ 逐药徽标会把一条 dsi.ppi_b12 归因到无关的药 = 编造因果。
    // 故:恰好 1 条**卡级**提示条, 且**没有**任何逐药标记。这条红 = 有人把逐药徽标加回来了。
    const { getAllByText } = render(<MedicationListCardView data={data} />);
    expect(getAllByText('1 条用药安全提示 · 详见安全告警')).toHaveLength(1);
  });

  it('never renders a per-drug safety badge even if a stale backend still sends has_safety_alert', () => {
    // 老后端/回滚期可能仍吐逐药字段 —— 卡片必须忽略它, 绝不逐药归因。
    const stale = {
      medications: [
        { name: '沃克（伏诺拉生）', has_safety_alert: true },
        { name: '铝碳酸镁', has_safety_alert: false },
      ],
      total: 2,
      safety_alert_count: 1,
    };
    const { queryAllByText, getAllByText } = render(<MedicationListCardView data={stale} />);
    expect(queryAllByText('安全提示')).toHaveLength(0); // 无裸「安全提示」逐药徽标
    expect(getAllByText('1 条用药安全提示 · 详见安全告警')).toHaveLength(1); // 只有卡级那条
  });

  it('omits the header alert count when safety_alert_count is 0', () => {
    const { getByText, queryAllByText } = render(
      <MedicationListCardView
        data={{ medications: [{ name: '沃克（伏诺拉生）' }], total: 1, safety_alert_count: 0 }}
      />,
    );
    expect(getByText('共 1 条')).toBeTruthy();
    expect(queryAllByText(/用药安全提示/)).toHaveLength(0);
  });

  it('degrades gracefully: only name / missing fields / empty / undefined never render null-ish text', () => {
    const { queryByText, getByText } = render(
      <MedicationListCardView data={{ medications: [{ name: '沃克（伏诺拉生）' }] }} />,
    );
    expect(getByText('沃克（伏诺拉生）')).toBeTruthy();
    for (const junk of ['null', 'undefined', 'NaN', '20mg · ', ' · ']) {
      expect(queryByText(junk)).toBeNull();
    }
    // total 缺失 → 退到实际渲染条数(可观察事实),不编造。
    expect(getByText('共 1 条')).toBeTruthy();

    expect(() => render(<MedicationListCardView data={{ medications: [] }} />)).not.toThrow();
    expect(() => render(<MedicationListCardView data={{}} />)).not.toThrow();
    expect(() => render(<MedicationListCardView data={undefined} />)).not.toThrow();
    expect(() =>
      render(<MedicationListCardView data={{ medications: [null, 'x', { dosage: '20mg' }] }} />),
    ).not.toThrow();
  });

  it('drops entries without a name (an unnamed drug must not be presented)', () => {
    const { queryByText } = render(
      <MedicationListCardView data={{ medications: [{ dosage: '20mg', category: '胃药' }] }} />,
    );
    expect(queryByText('20mg')).toBeNull();
    expect(queryByText('胃药')).toBeNull();
  });
});

// fence → parser → 卡片 的跨端消费者测试:没有 parser 分支 = 卡片静默丢弃(本仓库栽过的坑)。
describe('medication_list fence → parser → card', () => {
  const payload = JSON.stringify({ type: 'medication_list', v: 1, data });

  it('turns a fenced reva-ui medication_list into a card descriptor (inner data)', () => {
    const result = extractRevaUiBlocks(`你在吃的胃药:\n\n\`\`\`reva-ui\n${payload}\n\`\`\`\n\n仅供参考。`);
    expect(result.cards).toHaveLength(1);
    expect(result.cards[0].type).toBe('medication_list');
    expect(result.cards[0].data).toEqual(data);
    expect(result.cards[0].data.medications[0].name).toBe('沃克（伏诺拉生）');
    expect(result.text).toBe('你在吃的胃药:\n\n仅供参考。');
  });

  it('is registered in CARD_MAP and renders the drug name end-to-end', () => {
    expect(CARD_MAP['medication_list']).toBeTruthy();
    const { cards } = extractRevaUiBlocks(`\`\`\`reva-ui\n${payload}\n\`\`\``);
    const el = renderCard(cards[0]);
    expect(el).toBeTruthy();
    const { getByText } = render(el!);
    expect(getByText('沃克（伏诺拉生）')).toBeTruthy();
    expect(getByText('瑞巴派特')).toBeTruthy();
  });

  it('rejects a medication_list fence with string version "v1" (contract must be integer 1)', () => {
    const result = extractRevaUiBlocks(
      '前言\n```reva-ui\n{"type":"medication_list","v":"v1","data":{"medications":[{"name":"沃克"}]}}\n```\n结尾',
    );
    expect(result.cards).toHaveLength(0);
  });

  it('rejects a medication_list fence with a future version 2', () => {
    const result = extractRevaUiBlocks(
      '前言\n```reva-ui\n{"type":"medication_list","v":2,"data":{"medications":[{"name":"沃克"}]}}\n```\n结尾',
    );
    expect(result.cards).toHaveLength(0);
  });

  it('rejects a medication_list fence whose data is missing/non-object', () => {
    expect(extractRevaUiBlocks('```reva-ui\n{"type":"medication_list","v":1}\n```').cards).toHaveLength(0);
    expect(
      extractRevaUiBlocks('```reva-ui\n{"type":"medication_list","v":1,"data":"x"}\n```').cards,
    ).toHaveLength(0);
  });
});

describe('medication_list client cap', () => {
  it('declares genui-medication-list-v1 so the backend actually emits the card', () => {
    expect(buildClientCapsHeader()).toContain('genui-medication-list-v1');
  });
});
