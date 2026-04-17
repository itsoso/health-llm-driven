import api from './api';

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export interface WaterRecord {
  id: number;
  record_date: string;
  amount: number;
  drink_type: string;
}

export const supplementApi = {
  recordSupplement: async (supplementId: number, date: string) =>
    api.post('/supplements/records', { supplement_id: supplementId, record_date: date, taken: true }),
  deleteSupplementRecord: async (supplementId: number, date: string) =>
    api.delete(`/supplements/records/${supplementId}?record_date=${date}`),
};

export async function recordWater(amount: number): Promise<WaterRecord> {
  const { data } = await api.post<WaterRecord>('/water/records', {
    record_date: today(),
    amount,
    drink_type: '水',
    user_id: 0,
  });
  return data;
}

export async function deleteWater(id: number): Promise<void> {
  await api.delete(`/water/records/${id}`);
}

export async function updateCheckin(
  field: string,
  value: number,
): Promise<any> {
  const { data } = await api.post('/checkin/', {
    checkin_date: today(),
    [field]: value,
  });
  return data;
}
