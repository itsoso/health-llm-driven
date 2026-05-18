import { splitTextForCloudTts } from '../ttsText';

describe('splitTextForCloudTts', () => {
  it('keeps every cloud TTS chunk under backend text limit', () => {
    const text = Array.from({ length: 40 }, (_, i) => (
      `第${i + 1}条建议需要结合体检、运动、睡眠和饮食数据综合判断，优先给出可执行动作。`
    )).join(' ');

    const chunks = splitTextForCloudTts(text);

    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks.every(chunk => chunk.length <= 480)).toBe(true);
    expect(chunks.join(' ')).toContain('第1条建议');
    expect(chunks.join(' ')).toContain('第40条建议');
  });

  it('does not split decimal numbers as sentence endings', () => {
    const chunks = splitTextForCloudTts('今天跑了 3.6 公里。睡眠 7.5 小时，需要恢复。', 20);

    expect(chunks.join('|')).toContain('3.6 公里');
    expect(chunks.join('|')).toContain('7.5 小时');
  });

  it('hard wraps a single long sentence without punctuation', () => {
    const chunks = splitTextForCloudTts('补剂'.repeat(300), 100);

    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks.every(chunk => chunk.length <= 100)).toBe(true);
  });
});
