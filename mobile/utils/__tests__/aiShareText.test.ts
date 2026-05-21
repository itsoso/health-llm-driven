import { buildAiShareMessage } from '../aiShareText';

describe('buildAiShareMessage', () => {
  it('preserves markdown tables so the shared web page can render them', () => {
    const content = [
      '5月21日 健康简报',
      '',
      '| 指标 | 数值 | 状态 |',
      '| --- | --- | --- |',
      '| 睡眠 | 95分 | ✅ 优秀 |',
      '| 饮水 | 0ml/2000ml | ⚠️ 未达标 |',
    ].join('\n');

    expect(buildAiShareMessage(content)).toBe(`${content}\n\n— 健康 Agent`);
  });
});
