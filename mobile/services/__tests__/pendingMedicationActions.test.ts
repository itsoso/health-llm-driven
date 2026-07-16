import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  enqueuePendingMedicationAction,
  listPendingMedicationActions,
  removePendingMedicationAction,
} from '../pendingMedicationActions';

const actionFor = (date: string, medicationId = 7) => ({
  action: 'TAKEN' as const,
  data: {
    reminder_type: 'medication' as const,
    medication_id: medicationId,
    scheduled_date: date,
    scheduled_time: '08:30',
    scheduled_timezone: 'Asia/Shanghai',
    rule_id: `medication_reminder.${medicationId}.${date}.08:30`,
  },
});

describe('pendingMedicationActions', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
  });

  it('persists multiple offline occurrences without replacing the earlier action', async () => {
    await enqueuePendingMedicationAction(actionFor('2026-07-21'));
    await enqueuePendingMedicationAction(actionFor('2026-07-22'));

    const pending = await listPendingMedicationActions();
    expect(pending).toHaveLength(2);
    expect(pending.map((item) => item.data.scheduled_date)).toEqual([
      '2026-07-21',
      '2026-07-22',
    ]);
  });

  it('deduplicates the same occurrence and removes only the acknowledged action', async () => {
    const first = await enqueuePendingMedicationAction(actionFor('2026-07-21'));
    await enqueuePendingMedicationAction(actionFor('2026-07-21'));
    await enqueuePendingMedicationAction(actionFor('2026-07-22'));

    expect(await listPendingMedicationActions()).toHaveLength(2);
    await removePendingMedicationAction(first.key);

    const pending = await listPendingMedicationActions();
    expect(pending).toHaveLength(1);
    expect(pending[0].data.scheduled_date).toBe('2026-07-22');
  });

  it('does not silently drop older medication check-ins during a long offline period', async () => {
    for (let medicationId = 1; medicationId <= 40; medicationId += 1) {
      await enqueuePendingMedicationAction(actionFor('2026-07-21', medicationId));
    }

    const pending = await listPendingMedicationActions();
    expect(pending).toHaveLength(40);
    expect(pending[0].data.medication_id).toBe(1);
    expect(pending[39].data.medication_id).toBe(40);
  });
});
