import {
  AGENT_CONTEXT_MAX_CHARS,
  buildChatContextRoute,
  createActionCardAgentContext,
  createBodyMetricsAgentContext,
  createDietAgentContext,
  createDietPlanAgentContext,
  createHydrationAgentContext,
  createMedicationAgentContext,
  createMovementPlanAgentContext,
  createSafetyAlertAgentContext,
  createSleepSpo2AgentContext,
  createSupplementAgentContext,
  createSymptomAgentContext,
  createWorkoutDetailAgentContext,
  serializeAgentContext,
} from '../agentContext';

describe('agentContext', () => {
  it('builds chat route params with serialized context and badge', () => {
    const route = buildChatContextRoute({
      prompt: '今天饮食结构怎么样?',
      context: { from: 'diet/2026-05-14', date: '2026-05-14' },
      badge: '基于今日饮食 3 餐',
    });

    expect(route.pathname).toBe('/(tabs)/chat');
    expect(route.params.prompt).toBe('今天饮食结构怎么样?');
    expect(route.params.badge).toBe('基于今日饮食 3 餐');
    expect(JSON.parse(route.params.context)).toEqual({
      from: 'diet/2026-05-14',
      date: '2026-05-14',
    });
  });

  it('limits serialized context to the backend max length', () => {
    const context = serializeAgentContext({
      from: 'oversized',
      text: 'x'.repeat(AGENT_CONTEXT_MAX_CHARS + 500),
    });

    expect(context.length).toBeLessThanOrEqual(AGENT_CONTEXT_MAX_CHARS);
    expect(context).toContain('[truncated]');
  });

  it('creates compact diet context from daily summary', () => {
    const context = createDietAgentContext({
      record_date: '2026-05-14',
      total_calories: 1820,
      total_protein: 92,
      total_carbs: 180,
      total_fat: 58,
      total_fiber: 21,
      meals_count: 2,
      meals: [
        {
          id: 1,
          user_id: 1,
          record_date: '2026-05-14',
          meal_type: 'breakfast',
          food_items: '鸡蛋、燕麦',
          calories: 520,
          protein: 28,
          carbs: 60,
          fat: 18,
          fiber: 8,
          alcohol_units: null,
          image_url: null,
          notes: '训练前',
          health_tips: null,
        },
      ],
    });

    expect(context).toEqual({
      from: 'diet/2026-05-14',
      date: '2026-05-14',
      totals: {
        calories: 1820,
        protein: 92,
        carbs: 180,
        fat: 58,
        fiber: 21,
      },
      targets: null,
      meals: [
        {
          meal_type: 'breakfast',
          food_items: '鸡蛋、燕麦',
          calories: 520,
          protein: 28,
          carbs: 60,
          fat: 18,
          fiber: 8,
          notes: '训练前',
        },
      ],
    });
  });

  it('keeps safety alert rule context with the alert payload', () => {
    const context = createSafetyAlertAgentContext({
      rule_id: 'hrv_drop',
      severity: 'high',
      category: 'recovery',
      title: 'HRV 连续下降',
      message: 'HRV 低于 7 日均值 20%',
      action: '今晚降低训练强度',
      context: { hrv_today: 28, hrv_7d: 40 },
    });

    expect(context).toEqual({
      from: 'safety-alert/hrv_drop',
      alert_id: 'hrv_drop',
      rule_name: 'HRV 连续下降',
      severity: 'high',
      category: 'recovery',
      message: 'HRV 低于 7 日均值 20%',
      action: '今晚降低训练强度',
      triggered_metrics: { hrv_today: 28, hrv_7d: 40 },
    });
  });

  it('creates a compact single workout review context without route coordinates', () => {
    const context = createWorkoutDetailAgentContext({
      workout: {
        id: 42,
        user_id: 7,
        source: 'garmin',
        workout_date: '2026-05-21',
        workout_type: 'running',
        workout_name: 'Morning Run',
        start_time: '2026-05-21T07:10:00+08:00',
        end_time: '2026-05-21T07:55:00+08:00',
        duration_seconds: 2700,
        distance_meters: 8200,
        avg_heart_rate: 143,
        max_heart_rate: 171,
        calories: 520,
        steps: 8600,
        avg_speed_kmh: 10.9,
        max_speed_kmh: null,
        avg_pace_seconds_per_km: 330,
        avg_cadence: 172,
        max_cadence: null,
        avg_stride_length_cm: 104,
        elevation_gain_meters: 62,
        elevation_loss_meters: null,
        training_effect_aerobic: 3.2,
        training_effect_anaerobic: 0.8,
        vo2max: 48,
        training_load: 126,
        ai_analysis: null,
        post_workout_analysis: null,
        route_data: JSON.stringify([{ lat: 31.1, lng: 121.2 }]),
      },
      chart: {
        workout_id: 42,
        workout_type: 'running',
        duration_seconds: 2700,
        heart_rate_timeline: [{ time: 0, hr: 120 }, { time: 60, hr: 135 }],
        heart_rate_zones: [{ zone: 'Z3', minutes: 18, percentage: 40 }],
        pace_timeline: [{ time: 0, pace: 330 }],
        elevation_timeline: [{ distance: 1, elevation: 20 }],
        avg_heart_rate: 143,
        max_heart_rate: 171,
        avg_pace_display: `5'30"/km`,
        total_distance_km: 8.2,
        calories: 520,
      },
      analysis: {
        workout_id: 42,
        overall_rating: '良好',
        intensity_assessment: '中等偏上',
        heart_rate_analysis: '心率稳定',
        hr_zone_assessment: null,
        pace_analysis: '后半程略降速',
        training_effect_summary: '有氧效果明确',
        recovery_recommendation: '补水并放松小腿',
        next_workout_suggestion: '下次安排轻松跑',
        comparison_with_history: null,
        key_insights: ['配速稳定'],
        improvement_tips: ['加强跑后拉伸'],
      },
      postAnalysis: {
        success: true,
        recovery_tips: ['泡沫轴放松小腿', '补充碳水和蛋白'],
        improvement_tips: ['控制前 2 公里速度'],
      },
      postAnalysisMarkdown: '## 总评\n本次有氧基础不错。',
    });

    expect(context.from).toBe('workout/42');
    expect(context.feedback_intent).toBe('post_workout_review');
    expect(context.workout).toMatchObject({
      id: 42,
      type: 'running',
      duration_min: 45,
      distance_km: 8.2,
      has_route: true,
    });
    expect(JSON.stringify(context)).not.toContain('31.1');
    expect(context.chart).toMatchObject({
      heart_rate_samples_count: 2,
      pace_samples_count: 1,
      elevation_samples_count: 1,
    });
    expect(context.expected_agent_output).toEqual([
      '本次运动复盘',
      '拉伸与恢复建议',
      '下次训练安排',
      '需要用户补充反馈的问题',
    ]);
  });

  it('creates hydration feedback context from today water progress', () => {
    expect(createHydrationAgentContext({
      date: '2026-05-21',
      totalMl: 900,
      targetMl: 2000,
      records: [{ amount: 300, drink_type: '水' }, { amount: 600, drink_type: '电解质水' }],
    })).toEqual({
      from: 'hydration/2026-05-21',
      feedback_intent: 'hydration_adjustment',
      date: '2026-05-21',
      total_ml: 900,
      target_ml: 2000,
      progress_pct: 45,
      remaining_ml: 1100,
      records: [
        { amount_ml: 300, drink_type: '水', recorded_at: null },
        { amount_ml: 600, drink_type: '电解质水', recorded_at: null },
      ],
      expected_agent_output: ['今日饮水复盘', '接下来补水安排', '运动/睡眠/补剂相关注意事项'],
    });
  });

  it('creates supplement feedback context with pending items only summarised', () => {
    const context = createSupplementAgentContext({
      date: '2026-05-21',
      supplements: [
        { supplement: { id: 1, name: '维生素 D', timing: 'morning' }, record: { taken: true } },
        { id: 2, name: '镁', timing: 'bedtime', is_taken: false },
      ],
    });

    expect(context).toMatchObject({
      from: 'supplements/2026-05-21',
      feedback_intent: 'supplement_checkin_review',
      total: 2,
      taken: 1,
      pending: [{ id: 2, name: '镁', timing: 'bedtime' }],
    });
  });

  it('creates compact plan contexts for diet and movement plan follow-up', () => {
    const dietContext = createDietPlanAgentContext({
      has_data: true,
      summary: '今天蛋白质偏低',
      energy: { tdee_kcal: 2200, intake_kcal: 1600, remaining_kcal: 600, progress_pct: 73 },
      protein: { today_g: 58, target_g: 110, progress_pct: 53 },
      hydration: { ml_today: 900, goal_ml: 2000, progress_pct: 45, status: 'low' },
      supplement: { taken_today: 1, total: 3, pending: ['镁', '鱼油'] },
      proposed_experiments: [{ title: '早餐加蛋白', metric_key: 'protein' }],
      related_cards: [],
    });
    const movementContext = createMovementPlanAgentContext({
      has_data: true,
      summary: '本周训练负荷偏高',
      training_status: { status: 'overload', status_zh: '过载', acwr: 1.6, workouts_this_week: 4 },
      today: { intensity: 'low', intensity_zh: '低强度', guidance: '轻松跑或休息' },
      fitness: { vo2max_running: 48, resting_hr: 58 },
      proposed_experiments: [{ title: '降低强度', metric_key: 'hrv' }],
      related_cards: [],
    });

    expect(dietContext).toMatchObject({
      from: 'diet-plan/current',
      feedback_intent: 'diet_plan_follow_up',
      hydration: { ml_today: 900, goal_ml: 2000, status: 'low' },
    });
    expect(movementContext).toMatchObject({
      from: 'movement-plan/current',
      feedback_intent: 'movement_plan_follow_up',
      training_status: { status: 'overload', status_zh: '过载', acwr: 1.6 },
    });
  });

  it('creates action card feedback context with recommendation lifecycle fields', () => {
    const context = createActionCardAgentContext({
      id: 88,
      title: '连续 7 天晚饭后散步 20 分钟',
      content: '目标是降低餐后血糖波动。',
      card_type: 'plan',
      status: 'active',
      priority: 3,
      created_at: '2026-05-21T08:00:00Z',
      checklist: [{ item: '晚饭后散步', done: false }],
      metric_key: 'blood_glucose',
      baseline_value: '7.8 mmol/L',
      target_value: '< 7.0 mmol/L',
      actual_value: null,
      verification_days: 7,
      latest_assessment: { score: 6, summary: '执行还不足', evidence: ['只有 2 天记录'] },
      user_decision: 'accepted',
      outcome: null,
    } as any);

    expect(context).toMatchObject({
      from: 'action-card/88',
      feedback_intent: 'action_card_adjustment',
      card: {
        id: 88,
        title: '连续 7 天晚饭后散步 20 分钟',
        card_type: 'plan',
        status: 'active',
        metric_key: 'blood_glucose',
        baseline_value: '7.8 mmol/L',
        target_value: '< 7.0 mmol/L',
      },
      checklist: [{ item: '晚饭后散步', done: false }],
      latest_assessment: { score: 6, summary: '执行还不足', evidence: ['只有 2 天记录'] },
      expected_agent_output: ['判断建议是否仍适合', '调整执行方案', '复盘指标和体感反馈', '下一步行动'],
    });
  });

  it('creates body metrics feedback context for weight waist and blood pressure', () => {
    const context = createBodyMetricsAgentContext({
      date: '2026-05-21',
      latestWeightKg: 78.2,
      latestWeightDate: '2026-05-20',
      latestWaistCm: 89.5,
      latestWaistDate: '2026-05-20',
      weightStats: { current_weight: 78.2, weight_change_7d: -0.6 },
      bloodPressureStats: { average_systolic: 126, average_diastolic: 82 },
      draft: { weightKg: 78.0, waistCm: null, notes: '晨起空腹' },
    });

    expect(context).toEqual({
      from: 'body-metrics/2026-05-21',
      feedback_intent: 'body_metrics_review',
      date: '2026-05-21',
      latest: {
        weight_kg: 78.2,
        weight_date: '2026-05-20',
        waist_cm: 89.5,
        waist_date: '2026-05-20',
      },
      stats: {
        weight: { current_weight: 78.2, weight_change_7d: -0.6 },
        blood_pressure: { average_systolic: 126, average_diastolic: 82 },
      },
      draft_record: { weight_kg: 78.0, waist_cm: null, notes: '晨起空腹' },
      expected_agent_output: ['体重/腰围趋势复盘', '血压风险和生活方式建议', '今天饮食运动调整', '需要继续记录的数据'],
    });
  });

  it('creates symptom feedback context with safety boundary', () => {
    expect(createSymptomAgentContext({
      date: '2026-05-21',
      bodyPart: 'respiratory',
      description: '夜里咳嗽，有痰',
      severity: 5,
      source: 'manual',
    })).toEqual({
      from: 'symptom/2026-05-21',
      feedback_intent: 'symptom_triage_support',
      date: '2026-05-21',
      symptom: {
        body_part: 'respiratory',
        description: '夜里咳嗽，有痰',
        severity: 5,
        source: 'manual',
      },
      safety_boundary: '健康管理建议，不替代诊断；明显异常、急性加重或危险信号应及时就医。',
      expected_agent_output: ['症状复盘', '可能诱因和需要补充的问题', '居家观察与记录建议', '就医/急诊红旗信号'],
    });
  });

  it('creates sleep spo2 feedback context without raw timeseries', () => {
    const context = createSleepSpo2AgentContext({
      night_date: '2026-05-20',
      odi: 6.2,
      events_count: 9,
      min_spo2: 88,
      avg_spo2: 95,
      total_sleep_minutes: 420,
      events: [
        {
          start_ts: '01:00',
          end_ts: '01:01',
          duration_seconds: 45,
          min_spo2: 88,
          baseline_spo2: 96,
          drop_magnitude: 8,
          concurrent_hr_delta: 12,
          concurrent_respiration_rate: 17,
          sleep_stage: 'rem',
        },
      ],
      correlations: [
        {
          category: 'diagnostic',
          subject: '夜间低氧',
          rule: 'odi_ge_5',
          hypothesis: '可能存在睡眠呼吸风险',
          suggested_action: '观察并考虑进一步检查',
          severity: 'warning',
          confidence: 'medium',
          evidence: { odi: 6.2 },
        },
      ],
      action_priorities: ['今晚侧睡'],
      ask_questions: ['昨晚是否饮酒?'],
    });

    expect(context).toMatchObject({
      from: 'sleep-spo2/2026-05-20',
      feedback_intent: 'sleep_breathing_review',
      night: { odi: 6.2, events_count: 9, min_spo2: 88 },
      event_summary: [{ duration_seconds: 45, min_spo2: 88, sleep_stage: 'rem' }],
      expected_agent_output: ['昨晚呼吸风险复盘', '今晚睡眠实验建议', '需要补充的背景信息', '医生评估提示边界'],
    });
    expect(JSON.stringify(context)).not.toContain('start_ts');
  });

  it('creates medication feedback context with medical safety boundary', () => {
    const context = createMedicationAgentContext({
      date: '2026-05-21',
      activeMedications: [
        { id: 1, name: '鼻喷雾', dosage: '1 喷', frequency: '每日', purpose: '鼻炎', is_active: true },
      ] as any,
      archivedMedications: [
        { id: 2, name: '旧药', dosage: null, frequency: null, purpose: null, is_active: false },
      ] as any,
    });

    expect(context).toMatchObject({
      from: 'medications/2026-05-21',
      feedback_intent: 'medication_review_support',
      active_count: 1,
      archived_count: 1,
      active_medications: [{ id: 1, name: '鼻喷雾', dosage: '1 喷', frequency: '每日', purpose: '鼻炎' }],
      safety_boundary: '不能自行停药、换药或改剂量；只整理执行情况、疑问和就医沟通清单。',
    });
  });
});
