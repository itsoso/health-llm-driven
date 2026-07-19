import {
  commitLocalHealthMutation,
  getLocalHealthDecrypted,
  listLocalHealthDecrypted,
  type LocalHealthCollection,
  type LocalHealthMutation,
} from '../modules/local-health-kernel';
import type {
  DailyDietSummary,
  DietRecord,
  DietRecordCreate,
  DietRecordUpdate,
  DietStats,
  FrequentFood,
} from './diet';
import type { DietRepository } from './dietRepository';

export interface LocalDietKernelPort {
  get(collection: LocalHealthCollection, id: string): Promise<string | null>;
  list(collection: LocalHealthCollection, index: string, value: string): Promise<string[]>;
  commit(mutation: LocalHealthMutation): Promise<void>;
}

type LocalDietRepositoryDependencies = {
  nextRecordId: () => number;
  nextEventId: () => string;
  now: () => Date;
};

type StoredDietRecord = {
  schema_version: 1;
  owner_scope: string;
  object_version: number;
  created_at: string;
  updated_at: string;
  idempotency_key: string | null;
  record: DietRecord;
};

const nativeKernel: LocalDietKernelPort = {
  get: getLocalHealthDecrypted,
  list: listLocalHealthDecrypted,
  commit: commitLocalHealthMutation,
};

const finiteOrNull = (value: unknown): number | null => (
  typeof value === 'number' && Number.isFinite(value) ? value : null
);

function defaultRecordId(): number {
  const value = Date.now() * 1_000 + Math.floor(Math.random() * 1_000);
  if (!Number.isSafeInteger(value) || value <= 0) throw new Error('local_diet_id_failed');
  return value;
}

function defaultEventId(): string {
  return `event-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

function median(values: (number | null)[]): number | null {
  const sorted = values.filter((value): value is number => value !== null).sort((a, b) => a - b);
  if (!sorted.length) return null;
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function sumKnown(records: DietRecord[], key: 'calories' | 'protein' | 'carbs' | 'fat' | 'fiber') {
  return records.reduce((sum, record) => sum + (finiteOrNull(record[key]) ?? 0), 0);
}

function subtractDays(date: Date, days: number): string {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  copy.setDate(copy.getDate() - Math.max(0, days - 1));
  return `${copy.getFullYear()}-${String(copy.getMonth() + 1).padStart(2, '0')}-${String(copy.getDate()).padStart(2, '0')}`;
}

export class LocalDietRepository implements DietRepository {
  private readonly dependencies: LocalDietRepositoryDependencies;

  constructor(
    private readonly ownerScope: string,
    private readonly kernel: LocalDietKernelPort = nativeKernel,
    dependencies: Partial<LocalDietRepositoryDependencies> = {},
  ) {
    if (!ownerScope.trim()) throw new Error('local_diet_owner_missing');
    this.dependencies = {
      nextRecordId: dependencies.nextRecordId ?? defaultRecordId,
      nextEventId: dependencies.nextEventId ?? defaultEventId,
      now: dependencies.now ?? (() => new Date()),
    };
  }

  async getDailyDiet(date: string): Promise<DailyDietSummary> {
    const meals = (await this.kernel.list('diet_records', 'record_date', date))
      .map((payload) => this.parse(payload).record)
      .sort((a, b) => a.id - b.id);
    return {
      record_date: date,
      total_calories: sumKnown(meals, 'calories'),
      total_protein: sumKnown(meals, 'protein'),
      total_carbs: sumKnown(meals, 'carbs'),
      total_fat: sumKnown(meals, 'fat'),
      total_fiber: sumKnown(meals, 'fiber'),
      meals_count: meals.length,
      meals,
    };
  }

  async getDietStats(days = 7): Promise<DietStats> {
    const records = await this.activeRecords(days);
    const byDay = new Map<string, DietRecord[]>();
    for (const record of records) {
      const day = byDay.get(record.record_date) ?? [];
      day.push(record);
      byDay.set(record.record_date, day);
    }
    const dayValues = [...byDay.values()];
    const average = (key: 'calories' | 'protein' | 'carbs' | 'fat') => (
      dayValues.length
        ? dayValues.reduce((sum, meals) => sum + sumKnown(meals, key), 0) / dayValues.length
        : null
    );
    return {
      average_daily_calories: average('calories'),
      average_daily_protein: average('protein'),
      average_daily_carbs: average('carbs'),
      average_daily_fat: average('fat'),
      total_records: records.length,
      days_recorded: byDay.size,
    };
  }

  async getFrequentFoods(limit = 8, days = 30): Promise<FrequentFood[]> {
    const records = await this.activeRecords(days);
    const groups = new Map<string, DietRecord[]>();
    for (const record of records) {
      const key = `${record.meal_type}|${record.food_items.trim()}`;
      const group = groups.get(key) ?? [];
      group.push(record);
      groups.set(key, group);
    }
    return [...groups.values()]
      .map((group) => ({
        food_items: group[0].food_items,
        meal_type: group[0].meal_type,
        count: group.length,
        calories: median(group.map((item) => item.calories)),
        protein: median(group.map((item) => item.protein)),
        carbs: median(group.map((item) => item.carbs)),
        fat: median(group.map((item) => item.fat)),
      }))
      .sort((a, b) => b.count - a.count || a.food_items.localeCompare(b.food_items, 'zh-CN'))
      .slice(0, Math.max(0, limit));
  }

  async createDietRecord(input: DietRecordCreate): Promise<DietRecord> {
    this.validateCreate(input);
    if (input.idempotency_key) {
      const matches = await this.kernel.list('diet_records', 'idempotency', input.idempotency_key);
      if (matches.length > 1) throw new Error('local_diet_idempotency_conflict');
      if (matches[0]) return this.parse(matches[0]).record;
    }
    const id = this.dependencies.nextRecordId();
    if (!Number.isSafeInteger(id) || id <= 0) throw new Error('local_diet_id_failed');
    const now = this.dependencies.now().toISOString();
    const record: DietRecord = {
      id,
      user_id: 0,
      record_date: input.record_date,
      meal_type: input.meal_type,
      food_items: input.food_items.trim(),
      food_id: input.food_id ?? null,
      source: input.source ?? 'local_manual',
      calories: finiteOrNull(input.calories),
      protein: finiteOrNull(input.protein),
      carbs: finiteOrNull(input.carbs),
      fat: finiteOrNull(input.fat),
      fiber: finiteOrNull(input.fiber),
      alcohol_units: finiteOrNull(input.alcohol_units),
      image_url: null,
      notes: input.notes?.trim() || null,
      health_tips: null,
      ai_recognized: finiteOrNull(input.ai_recognized),
      ai_confidence: finiteOrNull(input.ai_confidence),
    };
    const stored: StoredDietRecord = {
      schema_version: 1,
      owner_scope: this.ownerScope,
      object_version: 1,
      created_at: now,
      updated_at: now,
      idempotency_key: input.idempotency_key ?? null,
      record,
    };
    await this.commitRecordMutation('diet_record_confirmed', stored, [], {
      record_date: record.record_date,
      lifecycle: 'active',
      ...(stored.idempotency_key ? { idempotency: stored.idempotency_key } : {}),
    });
    return record;
  }

  async updateDietRecord(id: number, patch: DietRecordUpdate): Promise<DietRecord> {
    const current = await this.requiredRecord(id);
    const record: DietRecord = {
      ...current.record,
      ...patch,
      id: current.record.id,
      user_id: 0,
      food_items: patch.food_items?.trim() || current.record.food_items,
      image_url: current.record.image_url,
    };
    this.validateRecord(record);
    const stored: StoredDietRecord = {
      ...current,
      object_version: current.object_version + 1,
      updated_at: this.dependencies.now().toISOString(),
      record,
    };
    await this.commitRecordMutation('diet_record_corrected', stored, [], {
      record_date: record.record_date,
      lifecycle: 'active',
      ...(stored.idempotency_key ? { idempotency: stored.idempotency_key } : {}),
    });
    return record;
  }

  async deleteDietRecord(id: number): Promise<void> {
    const current = await this.requiredRecord(id);
    await this.commitRecordMutation(
      'diet_record_deleted',
      null,
      [{ collection: 'diet_records', id: this.objectId(id) }],
      {},
      current,
    );
  }

  private async activeRecords(days: number): Promise<DietRecord[]> {
    const cutoff = subtractDays(this.dependencies.now(), days);
    return (await this.kernel.list('diet_records', 'lifecycle', 'active'))
      .map((payload) => this.parse(payload).record)
      .filter((record) => record.record_date >= cutoff);
  }

  private async requiredRecord(id: number): Promise<StoredDietRecord> {
    const payload = await this.kernel.get('diet_records', this.objectId(id));
    if (!payload) throw new Error('local_diet_record_not_found');
    return this.parse(payload);
  }

  private parse(payload: string): StoredDietRecord {
    let stored: StoredDietRecord;
    try {
      stored = JSON.parse(payload) as StoredDietRecord;
    } catch {
      throw new Error('local_diet_record_invalid');
    }
    if (stored?.schema_version !== 1 || stored.owner_scope !== this.ownerScope) {
      throw new Error(stored?.owner_scope === this.ownerScope
        ? 'local_diet_record_invalid'
        : 'local_diet_owner_mismatch');
    }
    if (!Number.isSafeInteger(stored.object_version) || stored.object_version < 1) {
      throw new Error('local_diet_record_invalid');
    }
    this.validateRecord(stored.record);
    return stored;
  }

  private validateCreate(record: Pick<DietRecordCreate, 'record_date' | 'meal_type' | 'food_items'>) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(record.record_date)
        || !['breakfast', 'lunch', 'dinner', 'snack'].includes(record.meal_type)
        || !record.food_items?.trim()) {
      throw new Error('local_diet_record_invalid');
    }
  }

  private validateRecord(record: DietRecord) {
    this.validateCreate(record);
    if (!Number.isSafeInteger(record.id) || record.id <= 0 || record.user_id !== 0) {
      throw new Error('local_diet_record_invalid');
    }
    for (const value of [record.calories, record.protein, record.carbs, record.fat,
      record.fiber, record.alcohol_units]) {
      if (value !== null && (typeof value !== 'number' || !Number.isFinite(value) || value < 0)) {
        throw new Error('local_diet_record_invalid');
      }
    }
  }

  private async commitRecordMutation(
    kind: string,
    stored: StoredDietRecord | null,
    deletes: LocalHealthMutation['deletes'],
    equalityIndexes: Record<string, string>,
    deleted?: StoredDietRecord,
  ) {
    const target = stored ?? deleted;
    if (!target) throw new Error('local_diet_record_invalid');
    const eventId = this.dependencies.nextEventId();
    const eventPayload = JSON.stringify({
      schema_version: 1,
      owner_scope: this.ownerScope,
      event_id: eventId,
      kind,
      record_id: target.record.id,
      record_version: target.object_version,
      occurred_at: this.dependencies.now().toISOString(),
    });
    const writes: LocalHealthMutation['writes'] = [];
    if (stored) {
      writes.push({
        collection: 'diet_records',
        id: this.objectId(stored.record.id),
        version: stored.object_version,
        equalityIndexes,
        payload: JSON.stringify(stored),
      });
    }
    writes.push({
      collection: 'execution_events',
      id: eventId,
      version: 1,
      equalityIndexes: {
        record_id: this.objectId(target.record.id),
        kind,
      },
      payload: eventPayload,
    });
    await this.kernel.commit({ writes, deletes });
  }

  private objectId(id: number): string {
    if (!Number.isSafeInteger(id) || id <= 0) throw new Error('local_diet_record_invalid');
    return `diet-${id}`;
  }
}
