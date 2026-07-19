import type {
  LocalHealthCollection,
  LocalHealthMutation,
} from '../../modules/local-health-kernel';
import {
  LocalDietRepository,
  type LocalDietKernelPort,
} from '../localDietRepository';

class MemoryKernel implements LocalDietKernelPort {
  readonly records = new Map<string, string>();
  readonly indexes = new Map<string, Map<string, Set<string>>>();
  readonly mutations: LocalHealthMutation[] = [];

  async get(collection: LocalHealthCollection, id: string): Promise<string | null> {
    return this.records.get(`${collection}|${id}`) ?? null;
  }

  async list(
    collection: LocalHealthCollection,
    index: string,
    value: string,
  ): Promise<string[]> {
    const ids = this.indexes.get(`${collection}|${index}`)?.get(value) ?? new Set();
    return [...ids].map((id) => this.records.get(`${collection}|${id}`)!).filter(Boolean);
  }

  async commit(mutation: LocalHealthMutation): Promise<void> {
    this.mutations.push(mutation);
    for (const write of mutation.writes) {
      const key = `${write.collection}|${write.id}`;
      this.removeIndexes(write.collection, write.id);
      this.records.set(key, write.payload);
      for (const [name, value] of Object.entries(write.equalityIndexes)) {
        const byValue = this.indexes.get(`${write.collection}|${name}`) ?? new Map();
        const ids = byValue.get(value) ?? new Set();
        ids.add(write.id);
        byValue.set(value, ids);
        this.indexes.set(`${write.collection}|${name}`, byValue);
      }
    }
    for (const deletion of mutation.deletes) {
      this.removeIndexes(deletion.collection, deletion.id);
      this.records.delete(`${deletion.collection}|${deletion.id}`);
    }
  }

  private removeIndexes(collection: LocalHealthCollection, id: string) {
    for (const [key, byValue] of this.indexes) {
      if (!key.startsWith(`${collection}|`)) continue;
      for (const ids of byValue.values()) ids.delete(id);
    }
  }
}

const meal = {
  record_date: '2026-07-19',
  meal_type: 'lunch' as const,
  food_items: '米饭和鸡蛋',
  calories: 360,
  protein: 16,
  carbs: 52,
  fat: 10,
  idempotency_key: 'confirm-once',
};

describe('LocalDietRepository', () => {
  let kernel: MemoryKernel;
  let nextId: number;
  let repository: LocalDietRepository;

  beforeEach(() => {
    kernel = new MemoryKernel();
    nextId = 100;
    repository = new LocalDietRepository('local-owner', kernel, {
      nextRecordId: () => nextId++,
      nextEventId: () => `event-${nextId++}`,
      now: () => new Date('2026-07-19T12:00:00.000Z'),
    });
  });

  it('creates, lists, updates and deletes through the repository contract', async () => {
    const created = await repository.createDietRecord(meal);
    expect(created).toMatchObject({ id: 100, food_items: '米饭和鸡蛋', user_id: 0 });

    const daily = await repository.getDailyDiet('2026-07-19');
    expect(daily.meals).toHaveLength(1);
    expect(daily).toMatchObject({ total_calories: 360, total_protein: 16, meals_count: 1 });

    await expect(repository.updateDietRecord(100, {
      food_items: '半碗米饭和两个鸡蛋',
      calories: 330,
    })).resolves.toMatchObject({ id: 100, calories: 330 });

    await repository.deleteDietRecord(100);
    await expect(repository.getDailyDiet('2026-07-19')).resolves.toMatchObject({ meals_count: 0 });
  });

  it('commits each record change with an append-only execution event', async () => {
    await repository.createDietRecord(meal);
    await repository.updateDietRecord(100, { notes: '少油' });
    await repository.deleteDietRecord(100);

    expect(kernel.mutations).toHaveLength(3);
    expect(kernel.mutations[0].writes.map((write) => write.collection)).toEqual([
      'diet_records',
      'execution_events',
    ]);
    expect(kernel.mutations[2]).toMatchObject({
      writes: [{ collection: 'execution_events' }],
      deletes: [{ collection: 'diet_records', id: 'diet-100' }],
    });
  });

  it('returns the existing record for a repeated idempotency key', async () => {
    const first = await repository.createDietRecord(meal);
    const second = await repository.createDietRecord({ ...meal, food_items: '不应覆盖' });

    expect(second).toEqual(first);
    expect(kernel.mutations).toHaveLength(1);
  });

  it('keeps unknown nutrition unknown and rejects foreign-owner payloads', async () => {
    await repository.createDietRecord({
      record_date: '2026-07-19',
      meal_type: 'snack',
      food_items: '自制点心',
    });
    const summary = await repository.getDailyDiet('2026-07-19');
    expect(summary.meals[0].calories).toBeNull();
    expect(summary.total_calories).toBe(0);

    const stored = JSON.parse(kernel.records.get('diet_records|diet-100')!);
    stored.owner_scope = 'different-owner';
    kernel.records.set('diet_records|diet-100', JSON.stringify(stored));
    await expect(repository.getDailyDiet('2026-07-19')).rejects.toThrow('local_diet_owner_mismatch');
  });

  it('derives frequent foods from encrypted local history', async () => {
    await repository.createDietRecord(meal);
    await repository.createDietRecord({
      ...meal,
      idempotency_key: 'second',
      record_date: '2026-07-18',
    });

    await expect(repository.getFrequentFoods(8, 30)).resolves.toEqual([
      expect.objectContaining({ food_items: '米饭和鸡蛋', count: 2, calories: 360 }),
    ]);
  });
});
