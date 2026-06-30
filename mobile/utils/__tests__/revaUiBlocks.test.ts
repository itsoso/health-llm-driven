import { extractRevaUiBlocks } from '../revaUiBlocks';

describe('extractRevaUiBlocks', () => {
  it('turns fenced reva-ui line_chart JSON into a renderable card descriptor', () => {
    const text = [
      '近半年 HRV 趋势如下:',
      '',
      '```reva-ui',
      '{"v":1,"component":"line_chart","title":"HRV 趋势","unit":"ms","x":["06-29","06-30"],"series":[{"name":"Garmin 夜间 HRV","role":"raw","points":[52,56]}],"annotations":[{"x":"06-30","label":"最新 56 ms · Garmin","kind":"latest"}],"source":"garmin","data_note":"基于 2 天真实数据"}',
      '```',
      '',
      '仅用于健康管理参考。',
    ].join('\n');

    const result = extractRevaUiBlocks(text);

    expect(result.text).toBe('近半年 HRV 趋势如下:\n\n仅用于健康管理参考。');
    expect(result.cards).toEqual([
      {
        type: 'line_chart',
        data: expect.objectContaining({
          component: 'line_chart',
          title: 'HRV 趋势',
          unit: 'ms',
        }),
      },
    ]);
  });

  it('strips unsupported or malformed reva-ui blocks instead of leaking raw JSON', () => {
    const result = extractRevaUiBlocks('说明\n```reva-ui\nnot-json\n```\n结束');

    expect(result.text).toBe('说明\n结束');
    expect(result.cards).toEqual([]);
  });
});
