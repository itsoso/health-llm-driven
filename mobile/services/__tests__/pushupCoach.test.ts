import {
  buildPushupExercisePayload,
  createPushupCoachState,
  createRokidPushupCoachCustomViewLayout,
  updatePushupCoach,
} from '../pushupCoach';

describe('pushupCoach', () => {
  it('counts one rep only after an up-down-up movement', () => {
    let state = createPushupCoachState({ targetReps: 20 });

    state = updatePushupCoach(state, {
      timestampMs: 0,
      elbowAngleDeg: 172,
      shoulderHipAnkleAngleDeg: 176,
      visibility: 0.95,
    });
    state = updatePushupCoach(state, {
      timestampMs: 700,
      elbowAngleDeg: 82,
      shoulderHipAnkleAngleDeg: 174,
      visibility: 0.94,
    });
    state = updatePushupCoach(state, {
      timestampMs: 1500,
      elbowAngleDeg: 166,
      shoulderHipAnkleAngleDeg: 175,
      visibility: 0.93,
    });

    expect(state.reps).toBe(1);
    expect(state.phase).toBe('up');
    expect(state.feedback).toContain('第 1 个完成');
    expect(state.qualityScore).toBeGreaterThanOrEqual(85);
  });

  it('does not count when the first visible pose starts from the bottom', () => {
    let state = createPushupCoachState();

    state = updatePushupCoach(state, { timestampMs: 0, elbowAngleDeg: 84, visibility: 0.95 });
    state = updatePushupCoach(state, { timestampMs: 900, elbowAngleDeg: 166, visibility: 0.95 });

    expect(state.reps).toBe(0);
    expect(state.phase).toBe('up');
  });

  it('ignores low-visibility and repeated down samples so noisy frames do not double count', () => {
    let state = createPushupCoachState();

    state = updatePushupCoach(state, { timestampMs: 0, elbowAngleDeg: 170, visibility: 0.92 });
    state = updatePushupCoach(state, { timestampMs: 300, elbowAngleDeg: 80, visibility: 0.32 });
    state = updatePushupCoach(state, { timestampMs: 650, elbowAngleDeg: 84, visibility: 0.94 });
    state = updatePushupCoach(state, { timestampMs: 900, elbowAngleDeg: 86, visibility: 0.93 });
    state = updatePushupCoach(state, { timestampMs: 1600, elbowAngleDeg: 164, visibility: 0.94 });
    state = updatePushupCoach(state, { timestampMs: 1880, elbowAngleDeg: 166, visibility: 0.93 });

    expect(state.reps).toBe(1);
    expect(state.formWarnings.some((warning) => warning.code === 'visibility_low')).toBe(false);
  });

  it('keeps shallow or loose-body reps but lowers quality and gives actionable coaching', () => {
    let state = createPushupCoachState();

    state = updatePushupCoach(state, {
      timestampMs: 0,
      elbowAngleDeg: 171,
      shoulderHipAnkleAngleDeg: 177,
      visibility: 0.95,
    });
    state = updatePushupCoach(state, {
      timestampMs: 600,
      elbowAngleDeg: 96,
      shoulderHipAnkleAngleDeg: 142,
      visibility: 0.95,
    });
    state = updatePushupCoach(state, {
      timestampMs: 1400,
      elbowAngleDeg: 165,
      shoulderHipAnkleAngleDeg: 146,
      visibility: 0.95,
    });

    expect(state.reps).toBe(1);
    expect(state.qualityScore).toBeLessThan(80);
    expect(state.formWarnings.map((warning) => warning.code)).toContain('body_line_soft');
    expect(state.suggestion).toContain('收紧');
  });

  it('builds a Rokid CustomView layout and exercise payload from the session', () => {
    let state = createPushupCoachState({ targetReps: 20 });
    state = updatePushupCoach(state, { timestampMs: 0, elbowAngleDeg: 172, visibility: 0.95 });
    state = updatePushupCoach(state, { timestampMs: 700, elbowAngleDeg: 82, visibility: 0.95 });
    state = updatePushupCoach(state, { timestampMs: 1500, elbowAngleDeg: 166, visibility: 0.95 });

    const view = JSON.parse(createRokidPushupCoachCustomViewLayout(state));
    expect(view.type).toBe('LinearLayout');
    expect(JSON.stringify(view)).toContain('俯卧撑计数');
    expect(JSON.stringify(view)).toContain('1 / 20');
    expect(JSON.stringify(view)).toContain(state.feedback);

    expect(buildPushupExercisePayload(state)).toMatchObject({
      exercise_type: '俯卧撑',
      reps: 1,
      sets: 1,
      intensity: 'moderate',
      source: 'rokid_glasses_pushup_coach',
    });
  });
});
