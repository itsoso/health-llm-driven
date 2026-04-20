import { CARD_REGISTRY, CARD_MAP, dispatchCard } from '../registry';
import type { CardContext } from '../types';

function makeContext(query: string, overrides?: Partial<CardContext>): CardContext {
  return {
    query,
    query_lower: query.toLowerCase(),
    toolsUsed: new Set(),
    data: {},
    api: { get: jest.fn(), post: jest.fn() },
    ...overrides,
  };
}

describe('CARD_REGISTRY', () => {
  it('has at least 10 registered cards', () => {
    expect(CARD_REGISTRY.length).toBeGreaterThanOrEqual(10);
  });

  it('each card has required fields', () => {
    for (const spec of CARD_REGISTRY) {
      expect(spec.type).toBeTruthy();
      expect(spec.label).toBeTruthy();
      expect(typeof spec.match).toBe('function');
      expect(typeof spec.build).toBe('function');
      expect(typeof spec.render).toBe('function');
    }
  });
});

describe('CARD_MAP', () => {
  it('maps all registry entries by type', () => {
    for (const spec of CARD_REGISTRY) {
      expect(CARD_MAP[spec.type]).toBe(spec);
    }
  });
});

describe('card match priorities', () => {
  it('sleep query matches sleep card', () => {
    const ctx = makeContext('我昨晚睡眠怎么样');
    const sleepSpec = CARD_REGISTRY.find((s) => s.type === 'sleep');
    expect(sleepSpec).toBeDefined();
    const score = sleepSpec!.match(ctx);
    expect(score).toBeGreaterThan(0);
  });

  it('weight query matches weight card', () => {
    const ctx = makeContext('我的体重多少');
    const weightSpec = CARD_REGISTRY.find((s) => s.type === 'weight');
    expect(weightSpec).toBeDefined();
    const score = weightSpec!.match(ctx);
    expect(score).toBeGreaterThan(0);
  });

  it('unrelated query does not match specific cards', () => {
    const ctx = makeContext('今天天气怎么样');
    const bpSpec = CARD_REGISTRY.find((s) => s.type === 'blood_pressure');
    expect(bpSpec).toBeDefined();
    const score = bpSpec!.match(ctx);
    expect(score === null || score === 0).toBe(true);
  });
});

describe('dispatchCard', () => {
  it('returns null for empty query with no matching cards', async () => {
    const ctx = makeContext('');
    const result = await dispatchCard(ctx);
    expect(result).toBeNull();
  });
});
