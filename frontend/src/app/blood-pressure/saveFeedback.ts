export interface BloodPressureSafetyGuidance {
  severity: 'high';
  recheck_instruction: string;
  emergency_instruction: string;
  action_path: string;
}

export interface BloodPressureSaveResult {
  message?: string;
  safety_guidance?: BloodPressureSafetyGuidance | null;
}

export function bloodPressureSaveFeedback(record: BloodPressureSaveResult): {
  message: string;
  type: 'success' | 'warning';
} {
  const guidance = record.safety_guidance;
  if (!guidance) {
    return { message: record.message || '血压记录保存成功！', type: 'success' };
  }
  return {
    message: `${record.message || '已记录。'} ${guidance.recheck_instruction} ${guidance.emergency_instruction}`,
    type: 'warning',
  };
}
