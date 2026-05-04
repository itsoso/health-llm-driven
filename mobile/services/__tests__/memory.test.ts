jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

import api from '../api';
import {
  listMemoryFacts,
  dismissMemoryFact,
  getMemoryStats,
  predicateLabel,
  tierLabel,
  groupByPredicate,
  type MemoryFact,
} from '../memory';

const mockGet = api.get as jest.Mock;
const mockPost = api.post as jest.Mock;

const makeFact = (overrides: Partial<MemoryFact> = {}): MemoryFact => ({
  id: 1,
  tier: 'semantic',
  subject: '你',
  predicate: 'has_symptom',
  object_value: '鼻塞',
  confidence: 0.8,
  effective_confidence: 0.75,
  reinforcement_count: 2,
  decay_rate: 0.02,
  sources: [],
  tags: [],
  is_sensitive: false,
  ...overrides,
});

describe('listMemoryFacts', () => {
  beforeEach(() => jest.clearAllMocks());

  it('calls /memory-facts/me without params when no filters', async () => {
    mockGet.mockResolvedValueOnce({ data: [makeFact()] });
    const out = await listMemoryFacts();
    expect(mockGet).toHaveBeenCalledWith('/memory-facts/me');
    expect(out).toHaveLength(1);
  });

  it('passes filters as query string', async () => {
    mockGet.mockResolvedValueOnce({ data: [] });
    await listMemoryFacts({ tier: 'semantic', limit: 100 });
    expect(mockGet).toHaveBeenCalledWith('/memory-facts/me?tier=semantic&limit=100');
  });

  it('returns empty array on shape error', async () => {
    mockGet.mockResolvedValueOnce({ data: undefined });
    expect(await listMemoryFacts()).toEqual([]);
  });

  it('returns empty array if data is not an array', async () => {
    mockGet.mockResolvedValueOnce({ data: { wrong: 'shape' } });
    expect(await listMemoryFacts()).toEqual([]);
  });
});

describe('dismissMemoryFact', () => {
  beforeEach(() => jest.clearAllMocks());

  it('posts to dismiss endpoint with default reason', async () => {
    mockPost.mockResolvedValueOnce({ data: { id: 1, dismissed: true } });
    await dismissMemoryFact(1);
    expect(mockPost).toHaveBeenCalledWith('/memory-facts/1/dismiss?reason=user_dismissed');
  });

  it('encodes custom reason in query', async () => {
    mockPost.mockResolvedValueOnce({ data: {} });
    await dismissMemoryFact(42, '不再服用了');
    expect(mockPost).toHaveBeenCalledWith(
      `/memory-facts/42/dismiss?reason=${encodeURIComponent('不再服用了')}`,
    );
  });
});

describe('getMemoryStats', () => {
  it('returns by_tier from response', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        by_tier: [
          { tier: 'semantic', total: 27, avg_confidence: 0.78 },
          { tier: 'episodic', total: 9, avg_confidence: 0.65 },
        ],
      },
    });
    const stats = await getMemoryStats();
    expect(stats.by_tier).toHaveLength(2);
    expect(stats.by_tier[0].tier).toBe('semantic');
  });

  it('returns empty stats on missing data', async () => {
    mockGet.mockResolvedValueOnce({ data: undefined });
    expect(await getMemoryStats()).toEqual({ by_tier: [] });
  });
});

describe('predicateLabel', () => {
  it('translates known predicates to Chinese', () => {
    expect(predicateLabel('has_symptom')).toBe('症状');
    expect(predicateLabel('takes_medication')).toBe('在服用');
    expect(predicateLabel('has_allergy')).toBe('过敏');
    expect(predicateLabel('prefers')).toBe('偏好');
    expect(predicateLabel('history_of')).toBe('病史');
  });

  it('falls back to raw predicate when not in map', () => {
    expect(predicateLabel('unknown_predicate')).toBe('unknown_predicate');
  });
});

describe('tierLabel', () => {
  it('translates 4 tiers', () => {
    expect(tierLabel('working')).toBe('临时');
    expect(tierLabel('episodic')).toBe('近期');
    expect(tierLabel('semantic')).toBe('长期');
    expect(tierLabel('procedural')).toBe('习惯');
  });
});

describe('groupByPredicate', () => {
  it('groups facts by predicate preserving order', () => {
    const facts = [
      makeFact({ id: 1, predicate: 'has_symptom', object_value: '鼻塞' }),
      makeFact({ id: 2, predicate: 'has_symptom', object_value: '咳嗽' }),
      makeFact({ id: 3, predicate: 'takes_medication', object_value: '异丙托溴铵' }),
    ];
    const out = groupByPredicate(facts);
    expect(out).toHaveLength(2);
    expect(out[0].predicate).toBe('has_symptom');
    expect(out[0].facts).toHaveLength(2);
    expect(out[0].label).toBe('症状');
    expect(out[1].predicate).toBe('takes_medication');
    expect(out[1].label).toBe('在服用');
  });

  it('handles empty list', () => {
    expect(groupByPredicate([])).toEqual([]);
  });
});
