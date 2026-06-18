export type PushupPhase = 'unknown' | 'up' | 'down' | 'transition';

export type PushupFormWarningCode =
  | 'visibility_low'
  | 'depth_shallow'
  | 'body_line_soft'
  | 'pace_too_fast';

export type PushupFormWarning = {
  code: PushupFormWarningCode;
  message: string;
};

export type PushupPoseSample = {
  timestampMs: number;
  elbowAngleDeg?: number;
  shoulderHipAnkleAngleDeg?: number;
  visibility?: number;
};

export type PushupCoachOptions = {
  targetReps?: number;
  downElbowDeg?: number;
  upElbowDeg?: number;
  minVisibility?: number;
  minRepIntervalMs?: number;
};

export type PushupCoachState = {
  reps: number;
  targetReps: number;
  phase: PushupPhase;
  qualityScore: number;
  feedback: string;
  suggestion: string;
  formWarnings: PushupFormWarning[];
  startedAtMs?: number;
  lastSampleAtMs?: number;
  lastRepAtMs?: number;
  lastPhaseChangeAtMs?: number;
  readyForRep: boolean;
  pendingDownAtMs?: number;
  pendingMinElbowDeg?: number;
  pendingWarnings: PushupFormWarning[];
  options: Required<PushupCoachOptions>;
};

const DEFAULT_OPTIONS: Required<PushupCoachOptions> = {
  targetReps: 20,
  downElbowDeg: 100,
  upElbowDeg: 155,
  minVisibility: 0.55,
  minRepIntervalMs: 800,
};

function uniqueWarnings(warnings: PushupFormWarning[]): PushupFormWarning[] {
  const seen = new Set<string>();
  return warnings.filter((warning) => {
    if (seen.has(warning.code)) {
      return false;
    }
    seen.add(warning.code);
    return true;
  });
}

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function classifyPhase(sample: PushupPoseSample, state: PushupCoachState): PushupPhase {
  if (sample.visibility != null && sample.visibility < state.options.minVisibility) {
    return 'unknown';
  }
  if (sample.elbowAngleDeg == null) {
    return 'transition';
  }
  if (sample.elbowAngleDeg <= state.options.downElbowDeg) {
    return 'down';
  }
  if (sample.elbowAngleDeg >= state.options.upElbowDeg) {
    return 'up';
  }
  return 'transition';
}

function warningsForSample(sample: PushupPoseSample, state: PushupCoachState): PushupFormWarning[] {
  const warnings: PushupFormWarning[] = [];
  if (sample.visibility != null && sample.visibility < state.options.minVisibility) {
    warnings.push({
      code: 'visibility_low',
      message: '眼镜视野不稳定, 暂停计数。',
    });
    return warnings;
  }
  if (
    sample.elbowAngleDeg != null
    && sample.elbowAngleDeg <= state.options.downElbowDeg
    && sample.elbowAngleDeg > 92
  ) {
    warnings.push({
      code: 'depth_shallow',
      message: '下放略浅, 下一次接近 90 度再推起。',
    });
  }
  if (sample.shoulderHipAnkleAngleDeg != null && sample.shoulderHipAnkleAngleDeg < 155) {
    warnings.push({
      code: 'body_line_soft',
      message: '躯干线条松了, 收紧臀腹。',
    });
  }
  return warnings;
}

function qualityForWarnings(warnings: PushupFormWarning[]): number {
  let score = 95;
  for (const warning of warnings) {
    if (warning.code === 'body_line_soft') {
      score -= 24;
    } else if (warning.code === 'depth_shallow') {
      score -= 12;
    } else if (warning.code === 'pace_too_fast') {
      score -= 10;
    }
  }
  return Math.max(40, Math.min(100, score));
}

function feedbackForRep(reps: number, qualityScore: number, warnings: PushupFormWarning[], targetReps: number) {
  if (reps >= targetReps) {
    return `第 ${reps} 个完成, 已达到本组目标。`;
  }
  if (warnings.some((warning) => warning.code === 'body_line_soft')) {
    return `第 ${reps} 个完成, 先稳住身体线条。`;
  }
  if (warnings.some((warning) => warning.code === 'depth_shallow')) {
    return `第 ${reps} 个完成, 深度再多一点会更有效。`;
  }
  if (qualityScore >= 90) {
    return `第 ${reps} 个完成, 节奏很好。`;
  }
  return `第 ${reps} 个完成, 保持可控节奏。`;
}

function suggestionForWarnings(warnings: PushupFormWarning[], reps: number, targetReps: number) {
  if (warnings.some((warning) => warning.code === 'body_line_soft')) {
    return '收紧臀腹, 头颈、背部和腿保持一条线。';
  }
  if (warnings.some((warning) => warning.code === 'depth_shallow')) {
    return '下一次下放到肘角接近 90 度, 再完整推起。';
  }
  if (reps >= targetReps) {
    return '本组可以收尾, 休息 60-90 秒后再决定是否加一组。';
  }
  return '继续按同样节奏, 每个动作都先稳再推。';
}

export function createPushupCoachState(options?: PushupCoachOptions): PushupCoachState {
  const mergedOptions = { ...DEFAULT_OPTIONS, ...options };
  return {
    reps: 0,
    targetReps: mergedOptions.targetReps,
    phase: 'unknown',
    qualityScore: 100,
    feedback: '准备开始, 先撑稳身体线条。',
    suggestion: '眼镜视野里保留上半身和手臂, 从标准俯卧撑姿势开始。',
    formWarnings: [],
    readyForRep: false,
    pendingWarnings: [],
    options: mergedOptions,
  };
}

export function updatePushupCoach(state: PushupCoachState, sample: PushupPoseSample): PushupCoachState {
  const sampleWarnings = warningsForSample(sample, state);
  if (sampleWarnings.some((warning) => warning.code === 'visibility_low')) {
    return {
      ...state,
      lastSampleAtMs: sample.timestampMs,
      feedback: '暂时看不清动作, 本帧不计数。',
      suggestion: '把眼镜视野对准上半身和手臂, 或稍微侧前方站位。',
    };
  }

  const nextPhase = classifyPhase(sample, state);
  const startedAtMs = state.startedAtMs ?? sample.timestampMs;
  let nextState: PushupCoachState = {
    ...state,
    startedAtMs,
    lastSampleAtMs: sample.timestampMs,
  };

  if (nextPhase === 'down') {
    nextState = {
      ...nextState,
      phase: 'down',
      lastPhaseChangeAtMs: state.phase !== 'down' ? sample.timestampMs : state.lastPhaseChangeAtMs,
      pendingDownAtMs: state.pendingDownAtMs ?? sample.timestampMs,
      pendingMinElbowDeg: Math.min(
        state.pendingMinElbowDeg ?? Number.POSITIVE_INFINITY,
        sample.elbowAngleDeg ?? Number.POSITIVE_INFINITY,
      ),
      pendingWarnings: uniqueWarnings([...state.pendingWarnings, ...sampleWarnings]),
    };
    return nextState;
  }

  if (nextPhase === 'up') {
    const hadDownPhase = state.readyForRep && state.phase === 'down' && state.pendingDownAtMs != null;
    const lastRepGap = state.lastRepAtMs == null
      ? Number.POSITIVE_INFINITY
      : sample.timestampMs - state.lastRepAtMs;

    if (hadDownPhase && lastRepGap >= state.options.minRepIntervalMs) {
      const durationMs = sample.timestampMs - (state.pendingDownAtMs ?? sample.timestampMs);
      const repWarnings = uniqueWarnings([
        ...state.pendingWarnings,
        ...sampleWarnings,
        ...(durationMs < 300
          ? [{ code: 'pace_too_fast' as const, message: '动作太快, 下放和推起都要可控。' }]
          : []),
      ]);
      const reps = state.reps + 1;
      const qualityScore = qualityForWarnings(repWarnings);
      return {
        ...nextState,
        reps,
        phase: 'up',
        readyForRep: true,
        qualityScore,
        feedback: feedbackForRep(reps, qualityScore, repWarnings, state.targetReps),
        suggestion: suggestionForWarnings(repWarnings, reps, state.targetReps),
        formWarnings: repWarnings,
        lastRepAtMs: sample.timestampMs,
        lastPhaseChangeAtMs: sample.timestampMs,
        pendingDownAtMs: undefined,
        pendingMinElbowDeg: undefined,
        pendingWarnings: [],
      };
    }

    return {
      ...nextState,
      phase: 'up',
      readyForRep: true,
      lastPhaseChangeAtMs: state.phase !== 'up' ? sample.timestampMs : state.lastPhaseChangeAtMs,
      pendingDownAtMs: undefined,
      pendingMinElbowDeg: undefined,
      pendingWarnings: [],
    };
  }

  if (nextPhase === 'transition') {
    return {
      ...nextState,
      phase: state.phase === 'unknown' ? 'transition' : state.phase,
      pendingWarnings: uniqueWarnings([...state.pendingWarnings, ...sampleWarnings]),
    };
  }

  return nextState;
}

export function createRokidPushupCoachCustomViewLayout(state: PushupCoachState): string {
  const countText = `${state.reps} / ${state.targetReps}`;
  const warningText = state.formWarnings.length > 0
    ? state.formWarnings.map((warning) => warning.message).join(' ')
    : '动作稳定时会自动计数。';
  return JSON.stringify({
    type: 'LinearLayout',
    props: {
      id: 'reva_pushup_root',
      layout_width: 'match_parent',
      layout_height: 'match_parent',
      orientation: 'vertical',
      gravity: 'center_vertical',
      paddingStart: '28dp',
      paddingEnd: '28dp',
      paddingTop: '96dp',
      paddingBottom: '88dp',
      backgroundColor: '#FF05070A',
    },
    children: [
      {
        type: 'TextView',
        props: {
          id: 'reva_pushup_title',
          layout_width: 'wrap_content',
          layout_height: 'wrap_content',
          text: '俯卧撑计数',
          textColor: '#FFFFFFFF',
          textSize: '18sp',
          textStyle: 'bold',
          marginBottom: '18dp',
        },
      },
      {
        type: 'TextView',
        props: {
          id: 'reva_pushup_count',
          layout_width: 'wrap_content',
          layout_height: 'wrap_content',
          text: countText,
          textColor: '#FFFFB057',
          textSize: '42sp',
          textStyle: 'bold',
          gravity: 'center',
          marginBottom: '16dp',
        },
      },
      {
        type: 'TextView',
        props: {
          id: 'reva_pushup_feedback',
          layout_width: 'match_parent',
          layout_height: 'wrap_content',
          text: state.feedback,
          textColor: '#FFE8F0FF',
          textSize: '15sp',
          gravity: 'center',
          marginBottom: '12dp',
        },
      },
      {
        type: 'TextView',
        props: {
          id: 'reva_pushup_suggestion',
          layout_width: 'match_parent',
          layout_height: 'wrap_content',
          text: state.suggestion,
          textColor: '#FF9CCBFF',
          textSize: '13sp',
          gravity: 'center',
          marginBottom: '10dp',
        },
      },
      {
        type: 'TextView',
        props: {
          id: 'reva_pushup_warning',
          layout_width: 'match_parent',
          layout_height: 'wrap_content',
          text: warningText,
          textColor: '#FFB8C3D6',
          textSize: '11sp',
          gravity: 'center',
        },
      },
    ],
  });
}

export function buildPushupExercisePayload(state: PushupCoachState) {
  return {
    record_date: today(),
    exercise_type: '俯卧撑',
    reps: state.reps,
    sets: 1,
    intensity: state.qualityScore >= 85 ? 'moderate' : 'low',
    source: 'rokid_glasses_pushup_coach',
    notes: `Rokid 俯卧撑计数: ${state.reps}/${state.targetReps}; quality=${state.qualityScore}; ${state.suggestion}`,
  };
}
