import {
  AGENT_CONTEXT_MAX_CHARS,
  buildChatContextRoute,
  createActionCardAgentContext,
  createAiProfileAgentContext,
  createBodyMetricsAgentContext,
  createDietAgentContext,
  createDietPlanAgentContext,
  createDirectivesAgentContext,
  createEnvironmentAgentContext,
  createExamExplainAgentContext,
  createGeneticReportAgentContext,
  createGoalsAgentContext,
  createHydrationAgentContext,
  createImportResultAgentContext,
  createLiveRunAgentContext,
  createMemoryAgentContext,
  createMedicationAgentContext,
  createMonthlyReportAgentContext,
  createMovementPlanAgentContext,
  createSafetyAlertAgentContext,
  createSleepSpo2AgentContext,
  createSpecialistScorecardAgentContext,
  createSupplementAgentContext,
  createSymptomAgentContext,
  createTrendAgentContext,
  createWeeklyBriefingAgentContext,
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
    expect(route.params.newChat).toBe('1');
    expect(route.params.contextEntry).toBe('1');
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
      related_cards: [{
        id: 11,
        title: '早餐加蛋白',
        status: 'active',
        user_decision: 'accepted',
        outcome: 'improved',
        effect_size: 0.2,
        metric_key: 'protein',
        baseline_value: '58g',
        actual_value: '82g',
        evidence_level: 'high',
        evidence_refs: ['claim:c_protein_weight_loss_boundary'],
        created_at: '2026-05-21T08:00:00Z',
        graded_at: null,
      }],
    });
    const movementContext = createMovementPlanAgentContext({
      has_data: true,
      summary: '本周训练负荷偏高',
      training_status: { status: 'overload', status_zh: '过载', acwr: 1.6, workouts_this_week: 4 },
      today: { intensity: 'low', intensity_zh: '低强度', guidance: '轻松跑或休息' },
      fitness: { vo2max_running: 48, resting_hr: 58 },
      proposed_experiments: [{ title: '降低强度', metric_key: 'hrv' }],
      related_cards: [{
        id: 12,
        title: '恢复差时降低训练强度',
        status: 'active',
        user_decision: 'accepted',
        outcome: 'unchanged',
        effect_size: 0,
        metric_key: 'hrv',
        baseline_value: '42',
        actual_value: '44',
        evidence_level: 'medium',
        evidence_refs: ['claim:c_recovery_low_reduce_intensity'],
        created_at: '2026-05-21T08:00:00Z',
        graded_at: null,
      }],
    });

    expect(dietContext).toMatchObject({
      from: 'diet-plan/current',
      feedback_intent: 'diet_plan_follow_up',
      hydration: { ml_today: 900, goal_ml: 2000, status: 'low' },
      related_cards: [{ evidence_refs: ['claim:c_protein_weight_loss_boundary'] }],
    });
    expect(movementContext).toMatchObject({
      from: 'movement-plan/current',
      feedback_intent: 'movement_plan_follow_up',
      training_status: { status: 'overload', status_zh: '过载', acwr: 1.6 },
      related_cards: [{ evidence_refs: ['claim:c_recovery_low_reduce_intensity'] }],
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

  it('creates trend feedback context from compact chart series', () => {
    const context = createTrendAgentContext({
      type: 'hrv',
      title: 'HRV 趋势',
      range: '1M',
      series: [{
        label: 'HRV',
        unit: 'ms',
        referenceRange: { low: 40, high: 100 },
        data: [
          { date: '2026-05-19', value: 58 },
          { date: '2026-05-20', value: 61 },
          { date: '2026-05-21', value: 63 },
        ],
      }],
    });

    expect(context).toMatchObject({
      from: 'indicator-history/hrv',
      feedback_intent: 'indicator_trend_review',
      title: 'HRV 趋势',
      range: '1M',
      latest: { label: 'HRV', date: '2026-05-21', value: 63, unit: 'ms' },
      reference_ranges: [{ label: 'HRV', low: 40, high: 100 }],
      expected_agent_output: ['趋势解读', '可能诱因', '下一步行动', '需要补充记录的数据'],
    });
  });

  it('creates exam explain feedback context with medical safety boundary', () => {
    const context = createExamExplainAgentContext({
      exam: { id: 7, exam_date: '2026-05-21', exam_type: '体检', hospital_name: '三甲医院' },
      abnormal_items: [
        { item_name: 'LDL-C', value: 3.8, unit: 'mmol/L', reference_range: '<3.4', is_abnormal: 'high', gene_links: ['APOE'] },
      ],
      user_gene_hits: [{ rsid: 'rs429358', gene: 'APOE', genotype: 'CT' }],
      explanation: {
        summary: 'LDL 偏高，需要结合生活方式和复查。',
        see_doctor_specialty: '心内科',
        recheck_window_days: 30,
        actions: [{ title: '减少饱和脂肪', category: 'diet', evidence_level: 'medium', metric_key: 'ldl' }],
      },
      trends: { 'LDL-C': [{ date: '2026-05-01', value: 3.6 }, { date: '2026-05-21', value: 3.8 }] },
      related_cards: [{ id: 11, title: '晚餐少油' }],
    });

    expect(context).toMatchObject({
      from: 'exam-explain/7',
      feedback_intent: 'exam_abnormal_review',
      exam: { date: '2026-05-21', type: '体检', hospital_name: '三甲医院' },
      abnormal_items: [{ name: 'LDL-C', value: 3.8, unit: 'mmol/L', flag: 'high', gene_links: ['APOE'] }],
      gene_hits: [{ rsid: 'rs429358', gene: 'APOE', genotype: 'CT' }],
      actions: [{ title: '减少饱和脂肪', category: 'diet', metric_key: 'ldl' }],
      safety_boundary: '用于健康管理和就医沟通准备，不替代诊断、治疗或用药建议。',
    });
  });

  it('creates genetic report feedback context without raw variants', () => {
    const context = createGeneticReportAgentContext({
      report: {
        profile: { id: 3, test_provider: 'WeGene', test_date: '2026-05-01' },
        stats: { hits: 38, miss: 14, total_known: 52 },
        clusters: [{ category: 'metabolic', hit_count: 8, high_risk_count: 2 }],
        items: [
          { rsid: 'rs1801133', gene: 'MTHFR', genotype: 'TT', category: 'methylation', hit: true, risk_level: 'high', title: '叶酸代谢' },
          { rsid: 'rs9939609', gene: 'FTO', genotype: 'AA', category: 'weight', hit: true, risk_level: 'medium', title: '体重管理' },
        ],
      },
      summary: '叶酸代谢和体重管理优先。',
      predictions: { disease_risk: { top_risks: [{ name: '冠心病', risk_level: 'medium' }] } },
    });

    expect(context).toMatchObject({
      from: 'genetic-report/current',
      feedback_intent: 'genetic_action_plan',
      profile: { provider: 'WeGene', test_date: '2026-05-01' },
      stats: { hits: 38, total_known: 52 },
      disease_risks: [{ name: '冠心病', risk_level: 'medium' }],
      safety_boundary: '基因结果只用于风险分层和生活方式建议，不等同疾病诊断。',
    });
    expect(context.top_hits).toEqual(expect.arrayContaining([
      expect.objectContaining({ rsid: 'rs1801133', gene: 'MTHFR', genotype: 'TT', risk_level: 'high' }),
    ]));
  });

  it('creates live run feedback context without GPS coordinates', () => {
    const context = createLiveRunAgentContext({
      id: 9,
      total_distance_m: 5200,
      total_duration_s: 1800,
      avg_pace_seconds: 346,
      max_hr: 171,
      z4_plus_minutes: 6.5,
      target_label: 'tempo',
      target_pace_seconds: 340,
      readiness_score: 72,
      narrative_status: 'completed',
      narrative: '后半程心率偏高。',
      gps_samples: [{ lat: 31.1, lon: 121.2 }],
      events: [{ rule_id: 'hr_overload', message: '心率过高', metric_snapshot: { hr: 171 } }],
    });

    expect(context).toMatchObject({
      from: 'live-run/9',
      feedback_intent: 'live_run_review',
      run: { distance_km: 5.2, duration_min: 30, avg_pace_seconds: 346, max_hr: 171 },
      target: { label: 'tempo', pace_seconds: 340, readiness_score: 72 },
      events: [{ rule_id: 'hr_overload', message: '心率过高' }],
      gps_samples_count: 1,
    });
    expect(JSON.stringify(context)).not.toContain('31.1');
  });

  it('creates weekly and monthly report feedback contexts', () => {
    const weekly = createWeeklyBriefingAgentContext({
      week_start: '2026-05-18',
      primary_goal: 'sleep',
      stats: { total: 3, accepted: 2, completed: 1, improved: 1 },
      cards: [{ id: 1, title: '提前睡觉', metric_key: 'sleep_score', baseline_value: '72', target_value: '80' }],
    });
    const monthly = createMonthlyReportAgentContext({
      year: 2026,
      month: 5,
      report: {
        coverage: { covered_days: 20, total_days: 31, pct: 65 },
        narrative: '睡眠有改善。',
        next_focus: ['稳定作息'],
        metric_trends: [{ metric: 'sleep_score', label: '睡眠评分', curr: 82, prev: 72, unit: '' }],
        ai_scorecard: { overall: { total_graded: 4, hit_rate: 50 }, top_hits: [], top_misses: [] },
        key_interventions: [{ kind: 'sleep', title: '早睡', date: '2026-05-10' }],
      },
    });

    expect(weekly).toMatchObject({
      from: 'weekly-briefing/2026-05-18',
      feedback_intent: 'weekly_briefing_review',
      cards: [{ id: 1, title: '提前睡觉', metric_key: 'sleep_score' }],
    });
    expect(monthly).toMatchObject({
      from: 'monthly-report/2026-05',
      feedback_intent: 'monthly_report_review',
      coverage: { covered_days: 20, total_days: 31, pct: 65 },
      next_focus: ['稳定作息'],
    });
  });

  it('creates goal profile memory directive import and environment contexts', () => {
    expect(createGoalsAgentContext([
      { id: 1, title: '降低体重', status: 'active', target_value: 75, current_value: 78, unit: 'kg' },
    ])).toMatchObject({
      from: 'goals/active',
      feedback_intent: 'goal_adjustment',
      active_goals: [{ id: 1, title: '降低体重', target_value: 75, current_value: 78 }],
    });

    expect(createAiProfileAgentContext({
      facts: [{ id: 2, tier: 'semantic', predicate: 'responds_to', object_value: '晚饭后散步', effective_confidence: 0.8 }],
      stats: { by_tier: [{ tier: 'semantic', total: 12, avg_confidence: 0.7 }] },
      scorecard: { window_days: 90, overall: { total: 5, hit_rate: 60, avg_score: 72 }, top_hits: [{ card_id: 3, title: '散步', score: 88 }] },
    })).toMatchObject({
      from: 'ai-profile/current',
      feedback_intent: 'ai_profile_correction',
      scorecard: { window_days: 90, hit_rate: 60 },
    });

    expect(createDirectivesAgentContext([
      { id: 4, kind: 'target_override', instruction: '血压控制在 130/80 以下', severity: 'mandatory', source: 'manual' },
    ])).toMatchObject({
      from: 'directives/active',
      feedback_intent: 'directive_review',
      directives: [{ id: 4, kind: 'target_override', severity: 'mandatory' }],
    });

    expect(createImportResultAgentContext({
      kind: 'medical_pdf',
      result: { message: '体检报告解析成功: 28 个指标', detail: '来源: 三甲医院' },
    })).toMatchObject({
      from: 'import/medical_pdf',
      feedback_intent: 'import_result_follow_up',
      result: { message: '体检报告解析成功: 28 个指标' },
    });

    expect(createEnvironmentAgentContext({
      weather: { temperature: 28, weather: '多云', humidity: 70 },
      airQuality: { aqi: 168, pm25: 82, primary_pollutant: 'PM2.5' },
      forecast: [{ date: '2026-05-22', weather: '雨', temp_max: 25, temp_min: 18 }],
      location: { city: '杭州', region: '浙江' },
    })).toMatchObject({
      from: 'environment/current',
      feedback_intent: 'environment_health_plan',
      location: { city: '杭州', region: '浙江' },
      air_quality: { aqi: 168, pm25: 82 },
    });
  });

  it('creates memory and specialist scorecard feedback contexts', () => {
    expect(createMemoryAgentContext({
      facts: [{ id: 9, tier: 'semantic', subject: 'user', predicate: 'prefers', object_value: '低强度跑', effective_confidence: 0.75 }],
      stats: { by_tier: [{ tier: 'semantic', total: 10, avg_confidence: 0.7 }] },
    })).toMatchObject({
      from: 'memory/current',
      feedback_intent: 'memory_correction',
      facts: [{ id: 9, predicate: 'prefers', object_value: '低强度跑' }],
    });

    expect(createSpecialistScorecardAgentContext({
      label: '运动',
      data: {
        specialist: 'movement_coach',
        window_days: 30,
        proposed_count: 5,
        graded_count: 3,
        hit_rate: 66,
        avg_accuracy: 74,
        cards: [{ id: 1, title: '轻松跑', metric_key: 'hrv', target_value: '回升', actual_value: '回升', accuracy_score: 88, why_short: '执行后 HRV 改善' }],
      },
    })).toMatchObject({
      from: 'specialist-scorecard/movement_coach',
      feedback_intent: 'specialist_scorecard_review',
      specialist: { name: 'movement_coach', label: '运动', window_days: 30, hit_rate: 66 },
      cards: [{ id: 1, title: '轻松跑', metric_key: 'hrv', accuracy_score: 88 }],
    });
  });
});
