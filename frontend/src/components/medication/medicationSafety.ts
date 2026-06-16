import type { MedicationItem, MedicationSafetyAlert } from '@/services/api/records';

export function collectMedicationSafetyAlerts(
  medications: MedicationItem[] | undefined,
): MedicationSafetyAlert[] {
  if (!Array.isArray(medications)) return [];
  return medications.flatMap((medication) => medication.safety_alerts ?? []);
}
