export interface BloodPressureSafetyGuidance {
  severity: 'high';
  title?: string;
  recheck_instruction: string;
  emergency_instruction: string;
  action_path: string;
}

export function bloodPressureSaveAlert(guidance?: BloodPressureSafetyGuidance | null): {
  title: string;
  message: string;
} | null {
  if (!guidance) return null;
  return {
    title: guidance.title || '血压严重升高，请复测',
    message: `${guidance.recheck_instruction}\n\n${guidance.emergency_instruction}`,
  };
}
