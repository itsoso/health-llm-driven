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
  batchCheckin: async (date: string, supplementId: number, taken: boolean) =>
    api.post('/supplements/records/batch', { record_date: date, checkins: [{ supplement_id: supplementId, taken }] }),
};

export interface FrequentSupplement {
  supplement_id: number;
  name: string;
  dosage: string | null;
  timing: string | null;
  count: number;
}

/** 最近最常打卡的补剂 (后端 /supplements/me/frequent). 点一下给今天打卡. */
export async function getFrequentSupplements(limit = 8, days = 30): Promise<FrequentSupplement[]> {
  const { data } = await api.get<FrequentSupplement[]>('/supplements/me/frequent', { params: { limit, days } });
  return data;
}

export interface FrequentWater {
  amount_ml: number;
  drink_type: string | null;
  count: number;
}

/** 最常用的「饮水量+饮品类型」组合 (后端 /water/records/me/frequent). 点一下直接记录. */
export async function getFrequentWater(limit = 6, days = 30): Promise<FrequentWater[]> {
  const { data } = await api.get<FrequentWater[]>('/water/records/me/frequent', { params: { limit, days } });
  return data;
}

export async function recordWater(amount: number, drinkType = '水'): Promise<WaterRecord> {
  const { data } = await api.post<WaterRecord>('/water/records', {
    record_date: today(),
    amount,
    drink_type: drinkType,
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
