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

  it('turns fenced reva-ui metric_line_chart JSON into a generic dynamic card descriptor', () => {
    const text = [
      '近半年心率趋势如下:',
      '',
      '```reva-ui',
      '{"v":1,"schema":"reva.metric_line_chart.v1","component":"metric_line_chart","metric":"resting_hr","range":"6m","title":"静息心率趋势","unit":"bpm","x":["06-29","06-30"],"series":[{"name":"Apple Watch 静息心率","role":"device","points":[62,58]}],"annotations":[{"x":"06-30","label":"最新 58 bpm · Apple Watch","kind":"latest"}],"source":"garmin","data_note":"基于 2 天真实数据"}',
      '```',
    ].join('\n');

    const result = extractRevaUiBlocks(text);

    expect(result.text).toBe('近半年心率趋势如下:');
    expect(result.cards).toEqual([
      {
        type: 'metric_line_chart',
        data: expect.objectContaining({
          component: 'metric_line_chart',
          metric: 'resting_hr',
          title: '静息心率趋势',
          unit: 'bpm',
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
