import { fireEvent, render } from '@testing-library/react-native';
import { renderCard, renderServerCards } from '../registry';

function visibleText(node: unknown): string[] {
  if (node == null) return [];
  if (typeof node === 'string' || typeof node === 'number') return [String(node)];
  if (Array.isArray(node)) return node.flatMap(visibleText);
  if (typeof node !== 'object') return [];
  return visibleText((node as { children?: unknown }).children);
}

describe('HealthEvidenceCard', () => {
  const descriptor = {
    type: 'health_evidence',
    data: {
      risk_level: 'high',
      sufficiency: 'clarify',
      verifier_verdict: 'pass',
      intent: {
        version: 'health-intent.v1',
        intent_id: 'health_advice.symptom.low_back_pain',
        intent: 'health_advice',
        domain: 'low_back_pain',
        risk_level: 'high',
      },
      red_flags: [
        {
          id: 'urgent-neurological-change',
          label: '如出现下肢无力或大小便失控，请立即就医',
        },
      ],
      authority_sources: [
        {
          source_id: 'nice-ng59',
          title: 'NICE 腰痛与坐骨神经痛指南',
          organization: 'NICE',
          source_kind: 'guideline',
          raw_excerpt: '不应由客户端展示的原文摘录',
        },
      ],
      evidence_refs: ['claim:low-back-triage'],
      authority_evidence_refs: ['claim:low-back-triage'],
      context_categories_used: [
        { category: 'symptoms', label: '症状时间线', raw_values: ['腰痛 8 分'] },
        { category: 'wearables', label: '可穿戴趋势', raw_values: { hrv: 12.3456 } },
      ],
      limitations: ['当前证据不能替代面诊和体格检查'],
      missing_discriminators: [
        {
          id: 'recent-trauma',
          label: '近期是否有跌倒或外伤？',
        },
      ],
      private_packet: {
        genetics: 'HLA-B*15:02 positive',
        medication_record_id: 42,
      },
    },
  };

  it('puts explicit red flags before evidence and context sections', () => {
    const element = renderCard(descriptor);
    expect(element).not.toBeNull();

    const screen = render(element!);
    const text = visibleText(screen.toJSON());
    const redFlagIndex = text.indexOf('如出现下肢无力或大小便失控，请立即就医');
    const sourceIndex = text.indexOf('NICE 腰痛与坐骨神经痛指南');
    const contextIndex = text.indexOf('症状时间线');

    expect(redFlagIndex).toBeGreaterThanOrEqual(0);
    expect(redFlagIndex).toBeLessThan(sourceIndex);
    expect(sourceIndex).toBeLessThan(contextIndex);
    expect(screen.getByText('高风险')).toBeTruthy();
  });

  it('renders only the backend public projection and its explicit gaps', () => {
    const screen = render(renderCard(descriptor)!);

    expect(screen.getByText('权威来源')).toBeTruthy();
    expect(screen.getByText('NICE 腰痛与坐骨神经痛指南')).toBeTruthy();
    expect(screen.getByText('NICE · 临床指南')).toBeTruthy();
    expect(screen.getByText('已用个人数据')).toBeTruthy();
    expect(screen.getByText('症状时间线')).toBeTruthy();
    expect(screen.getByText('可穿戴趋势')).toBeTruthy();
    expect(screen.getByText('限制与待确认')).toBeTruthy();
    expect(screen.getByText('当前证据不能替代面诊和体格检查')).toBeTruthy();
    expect(screen.getByText('近期是否有跌倒或外伤？')).toBeTruthy();

    expect(screen.queryByText('不应由客户端展示的原文摘录')).toBeNull();
    expect(screen.queryByText('腰痛 8 分')).toBeNull();
    expect(screen.queryByText('HLA-B*15:02 positive')).toBeNull();
    expect(screen.queryByText('42')).toBeNull();
  });

  it('accepts the backend descriptor and degrades safely when fields are absent', () => {
    const [projected] = renderServerCards([descriptor]);
    expect(projected.type).toBe('health_evidence');
    expect(projected.data).not.toHaveProperty('private_packet');
    expect(projected.data.authority_sources[0]).not.toHaveProperty('raw_excerpt');
    expect(projected.data.context_categories_used[0]).not.toHaveProperty('raw_values');

    const element = renderCard({
      type: 'health_evidence',
      data: {
        authority_sources: [{ raw_excerpt: 'private source body' }],
        context_categories_used: [{ raw_values: ['private health value'] }],
        missing_discriminators: [{ id: 'internal-only-id' }],
      },
    } as any);

    expect(element).not.toBeNull();
    const screen = render(element!);
    expect(screen.getByText('本轮暂无可展示的结构化证据详情')).toBeTruthy();
    expect(screen.queryByText('private source body')).toBeNull();
    expect(screen.queryByText('private health value')).toBeNull();
    expect(screen.queryByText('internal-only-id')).toBeNull();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  it('renders the current backend public-manifest aliases without exposing internal ids', () => {
    const element = renderCard({
      type: 'health_evidence',
      data: {
        risk_level: 'medium',
        sources: [
          {
            source: 'https://www.nice.org.uk/guidance/ng59',
            kind: 'guideline',
            organization: 'NICE',
            title: 'NICE 腰痛与坐骨神经痛指南',
            authority_tier: 'T1',
          },
        ],
        evidence_refs: ['claim:low-back-triage'],
        context_categories_used: ['symptom', 'medication'],
        gaps: [
          {
            gap_id: 'personal-gap:allergy',
            category: 'allergy',
            state: 'absent',
          },
        ],
        conflicts: [
          {
            conflict_id: 'personal-conflict:wearable',
            category: 'wearable',
          },
        ],
        truncated: true,
      },
    } as any);

    expect(element).not.toBeNull();
    const screen = render(element!);
    expect(screen.getByText('NICE 腰痛与坐骨神经痛指南')).toBeTruthy();
    expect(screen.getByText('NICE · 临床指南')).toBeTruthy();
    expect(screen.getByText('症状时间线')).toBeTruthy();
    expect(screen.getByText('当前用药类别')).toBeTruthy();
    expect(screen.getByText('缺少过敏史')).toBeTruthy();
    expect(screen.getByText('可穿戴趋势存在冲突记录')).toBeTruthy();
    expect(screen.getByText('本轮仅展示与问题最相关的个人数据类别')).toBeTruthy();
    expect(screen.queryByText('personal-gap:allergy')).toBeNull();
    expect(screen.queryByText('personal-conflict:wearable')).toBeNull();
  });

  it('collects every discriminator answer before one structured continuation submit', () => {
    const onSendSuggestedPrompt = jest.fn();
    const element = renderCard({
      type: 'health_evidence',
      data: {
        intent: {
          intent_id: 'health_advice.symptom.low_back_pain',
        },
        missing_discriminators: [
          {
            id: 'low_back.cauda_equina',
            question: '是否有排尿困难、大小便失控，或会阴/肛周麻木？',
            label: '确认膀胱、肠道及会阴感觉是否有新变化',
            choices: ['有', '没有', '不确定'],
            priority: 'emergency',
            is_red_flag: true,
          },
          {
            id: 'low_back.major_trauma',
            question: '近期是否有车祸、高处跌落或其他严重外伤？',
            label: '确认近期是否有严重外伤',
            choices: ['有', '没有', '不确定'],
            priority: 'urgent',
            is_red_flag: true,
          },
        ],
      },
    }, {
      onSendSuggestedPrompt,
      healthEvidenceParent: {
        messageRef: 314,
        turnRef: 'turn-parent-7',
      },
    });

    expect(element).not.toBeNull();
    const screen = render(element!);
    expect(screen.getByText('是否有排尿困难、大小便失控，或会阴/肛周麻木？')).toBeTruthy();

    fireEvent.press(screen.getByRole('button', {
      name: '是否有排尿困难、大小便失控，或会阴/肛周麻木？：没有',
    }));
    expect(onSendSuggestedPrompt).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '提交本轮追问回答' }).props.accessibilityState)
      .toEqual(expect.objectContaining({ disabled: true }));

    fireEvent.press(screen.getByRole('button', {
      name: '近期是否有车祸、高处跌落或其他严重外伤？：不确定',
    }));
    expect(onSendSuggestedPrompt).not.toHaveBeenCalled();

    fireEvent.press(screen.getByRole('button', { name: '提交本轮追问回答' }));

    expect(onSendSuggestedPrompt).toHaveBeenCalledTimes(1);
    const [prompt, extraContext] = onSendSuggestedPrompt.mock.calls[0];
    expect(prompt).toBe('我已完成本轮 2 项安全追问，请根据结构化回答继续分析。');
    expect(JSON.parse(extraContext)).toEqual({
      health_evidence_continuation: {
        version: 'health-evidence-continuation.v1',
        parent_intent_id: 'health_advice.symptom.low_back_pain',
        parent_message_id: 314,
        parent_turn_id: 'turn-parent-7',
        answers: [
          {
            discriminator_id: 'low_back.cauda_equina',
            answer: 'no',
          },
          {
            discriminator_id: 'low_back.major_trauma',
            answer: 'unknown',
          },
        ],
      },
    });
  });

  it('keeps unknown discriminators under pending exclusion instead of detected red flags', () => {
    const screen = render(renderCard({
      type: 'health_evidence',
      data: {
        risk_level: 'medium',
        missing_discriminators: [{
          id: 'low_back.major_trauma',
          question: '近期是否有严重外伤？',
          label: '确认近期是否有严重外伤',
          choices: ['有', '没有', '不确定'],
          priority: 'urgent',
          is_red_flag: true,
        }],
      },
    })!);

    expect(screen.getByText('待排除的警示征象')).toBeTruthy();
    expect(screen.queryByText('红旗提示 · 优先处理')).toBeNull();
  });

  it('renders conditional urgent precautions as safety boundaries, not detected flags', () => {
    const screen = render(renderCard({
      type: 'health_evidence',
      data: {
        risk_level: 'medium',
        urgent_red_flags: [{
          id: 'legacy-conditional-cauda-equina',
          label: '如有排尿困难或会阴麻木，请立即就医',
        }],
      },
    })!);

    expect(screen.getByText('安全边界 · 出现即就医')).toBeTruthy();
    expect(screen.getByText('如有排尿困难或会阴麻木，请立即就医')).toBeTruthy();
    expect(screen.queryByText('红旗提示 · 优先处理')).toBeNull();
  });

  it('does not count personal refs as reviewed authority evidence', () => {
    const screen = render(renderCard({
      type: 'health_evidence',
      data: {
        sufficiency: 'safe_fallback',
        evidence_refs: ['personal:symptom:1'],
        authority_evidence_refs: [],
        authority_sources: [],
      },
    })!);

    expect(screen.getByText('本轮没有可用的审定权威证据')).toBeTruthy();
    expect(screen.queryByText(/系统已使用 .* 条审定证据/)).toBeNull();
  });
});
