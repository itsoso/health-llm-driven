import {
  buildEvidenceProcessItems,
  buildEvidenceSummary,
} from '../AnswerEvidencePanel';
import { normalizeAnswerEvidence } from '../../../services/answerEvidence';

describe('AnswerEvidencePanel process summary', () => {
  it('uses completed language, preserves order, and removes duplicate status events', () => {
    expect(buildEvidenceProcessItems([
      '正在理解你的问题',
      '正在理解你的问题…',
      '正在查询健康数据',
      '整理回复中',
    ])).toEqual([
      { label: '理解你的问题', tone: 'complete' },
      { label: '查询健康数据', tone: 'complete' },
      { label: '整理回答', tone: 'complete' },
    ]);
  });

  it('describes health-data access as an action instead of claiming data was obtained', () => {
    expect(buildEvidenceProcessItems(['已取得健康数据'])).toEqual([
      { label: '检查健康数据', tone: 'complete' },
    ]);
  });

  it.each([
    '查询失败',
    '记录信息暂时不可用',
    '睡眠数据缺失',
    'Garmin 数据未同步',
    '已跳过可选检索',
  ])('marks an incomplete step as warning: %s', (step) => {
    expect(buildEvidenceProcessItems([step])).toEqual([{ label: step, tone: 'warning' }]);
  });

  it('does not count warning steps as completed work', () => {
    const items = buildEvidenceProcessItems([
      '理解你的问题',
      '睡眠数据暂时不可用',
      '整理回答',
    ]);

    expect(buildEvidenceSummary(3, items)).toEqual({
      title: '这条回答参考了 3 项信息',
      subtitle: '完成 2 个处理步骤，1 项需要注意',
      tone: 'warning',
    });
  });
});

describe('AnswerEvidencePanel structured evidence', () => {
  it('normalizes concrete basis and limitations from the done contract', () => {
    expect(normalizeAnswerEvidence({
      version: 'answer-evidence.v1',
      summary: '本轮获得 2 条可核对数据，1 项需注意',
      basis: [{
        id: 'wearable.hrv.latest',
        label: 'HRV',
        observation: '31 ms',
        context: '今天 07:55',
        source: 'Garmin',
        purpose: '用于评估恢复与活动承受度',
        freshness: 'current',
        confidence: 'high',
      }],
      limitations: [{
        id: 'wearable.resting-heart-rate',
        title: '静息心率未同步',
        detail: '昨晚没有可用记录',
        handling: '未按正常值处理，运动建议已保持保守',
      }],
    })).toEqual(expect.objectContaining({
      summary: '本轮获得 2 条可核对数据，1 项需注意',
      basis: [expect.objectContaining({ observation: '31 ms', source: 'Garmin' })],
      limitations: [expect.objectContaining({ title: '静息心率未同步' })],
    }));
  });

  it('rejects raw nested payloads instead of rendering them', () => {
    expect(normalizeAnswerEvidence({
      version: 'answer-evidence.v1',
      summary: '不可信',
      basis: [{
        id: 'raw',
        label: '原始载荷',
        observation: { private: true },
        source: 'tool',
      }],
      limitations: [],
    })).toBeUndefined();
  });
});
