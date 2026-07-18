import { bloodPressureSaveAlert } from '../bloodPressureSafety';

describe('bloodPressureSaveAlert', () => {
  it('returns visible recheck-and-triage content for a severe-reading response', () => {
    const alert = bloodPressureSaveAlert({
      severity: 'high',
      recheck_instruction: '请静坐至少 1 分钟后复测。',
      emergency_instruction: '若同时出现胸痛，请立即拨打急救电话。',
      action_path: '/blood-pressure',
    });

    expect(alert).toEqual({
      title: '血压严重升高，请复测',
      message: '请静坐至少 1 分钟后复测。\n\n若同时出现胸痛，请立即拨打急救电话。',
    });
  });

  it('does not show an alert for a normal response', () => {
    expect(bloodPressureSaveAlert(undefined)).toBeNull();
  });
});
