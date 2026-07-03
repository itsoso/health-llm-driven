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

  it('turns fenced reva-ui metric_empty_state JSON into a dynamic card descriptor', () => {
    const text = [
      '最近一周血糖暂无足够数据:',
      '',
      '```reva-ui',
      '{"v":1,"schema":"reva.metric_empty_state.v1","component":"metric_empty_state","metric":"blood_glucose","range":"7d","title":"血糖数据不足","message":"暂无足够数据，至少需要 3 天真实记录后才能生成趋势图。","suggestions":["同步 HealthKit 或可穿戴设备数据","补录最近几天的关键指标"],"boundary":"仅用于健康管理参考，不替代诊断或治疗。"}',
      '```',
    ].join('\n');

    const result = extractRevaUiBlocks(text);

    expect(result.text).toBe('最近一周血糖暂无足够数据:');
    expect(result.cards).toEqual([
      {
        type: 'metric_empty_state',
        data: expect.objectContaining({
          component: 'metric_empty_state',
          metric: 'blood_glucose',
          title: '血糖数据不足',
        }),
      },
    ]);
  });

  it('turns fenced reva-ui diet_draft JSON into a confirmable diet draft card', () => {
    const text = [
      '我识别到这是一份午餐:',
      '',
      '```reva-ui',
      '{"v":1,"schema":"reva.diet_draft.v1","component":"diet_draft","meal_type":"lunch","food_items":"煎牛肉能量碗 + 姜黄鲜柠维C茶","calories":770,"protein":30,"carbs":70,"fat":17,"confidence":0.82,"source":"chat_photo","suggestions":["晚餐优先补 40g 蛋白"],"post_meal_walk":{"recommended":true,"minutes":10},"boundary":"营养为估算值,确认后写入今日饮食记录。","actions":[{"id":"confirm-diet-draft","label":"确认记录","action":"diet_record.create","endpoint":"/diet/records","requires_manual_confirm":true,"payload":{"record":{"meal_type":"lunch","food_items":"煎牛肉能量碗 + 姜黄鲜柠维C茶","calories":770,"protein":30,"carbs":70,"fat":17}}}]}',
      '```',
    ].join('\n');

    const result = extractRevaUiBlocks(text);

    expect(result.text).toBe('我识别到这是一份午餐:');
    expect(result.cards).toEqual([
      {
        type: 'diet_draft',
        data: expect.objectContaining({
          component: 'diet_draft',
          meal_type: 'lunch',
          food_items: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
        }),
        actions: [
          expect.objectContaining({
            action: 'diet_record.create',
            endpoint: '/diet/records',
            requires_manual_confirm: true,
          }),
        ],
      },
    ]);
  });

  it('turns fenced reva-ui record_quality JSON into a diet quality card descriptor', () => {
    const text = [
      '午餐已经记录，下面是这餐之后的建议:',
      '',
      '```reva-ui',
      '{"v":1,"schema":"reva.record_quality.v1","component":"record_quality","domain":"diet","title":"午餐已记录","summary":"770 kcal · 蛋白 30g · 碳水 70g","metrics":[{"label":"热量","value":"770kcal"},{"label":"蛋白","value":"30g"}],"progress":{"protein_total_g":37,"protein_target_g":112,"remaining_protein_g":75,"calories_total":1040,"meals_count":2},"primary_judgement":"蛋白质到位，但晚餐仍要补足。","personal_cautions":["胃溃疡记录在案，冷饮/酸性饮品可能刺激胃。"],"next_action":"晚餐优先 40g 蛋白，少油少刺激。","boundary":"健康管理建议，不替代医生诊断或治疗。","actions":[{"id":"show-next-meal","label":"看下一餐建议","action":"ui.inline.expand","payload":{"target":"next_meal","patch":{"expanded_sections":["next_meal"],"next_meal_detail":{"title":"下一餐建议","summary":"鱼/豆腐 + 熟蔬菜 + 少量主食","options":["鱼/豆腐 + 熟蔬菜 + 少量主食"],"continue_prompt":"如果今晚只能外卖，怎么选？"}}}}]}',
      '```',
    ].join('\n');

    const result = extractRevaUiBlocks(text);

    expect(result.text).toBe('午餐已经记录，下面是这餐之后的建议:');
    expect(result.cards).toEqual([
      {
        type: 'record_quality',
        data: expect.objectContaining({
          component: 'record_quality',
          domain: 'diet',
          title: '午餐已记录',
          primary_judgement: '蛋白质到位，但晚餐仍要补足。',
        }),
        actions: [
          expect.objectContaining({
            action: 'ui.inline.expand',
            label: '看下一餐建议',
          }),
        ],
      },
    ]);
  });

  it('strips unsupported or malformed reva-ui blocks instead of leaking raw JSON', () => {
    const result = extractRevaUiBlocks('说明\n```reva-ui\nnot-json\n```\n结束');

    expect(result.text).toBe('说明\n结束');
    expect(result.cards).toEqual([]);
  });
});
