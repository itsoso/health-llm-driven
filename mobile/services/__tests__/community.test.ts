/* eslint-disable import/first */

const mockGet = jest.fn();
const mockPost = jest.fn();
const mockPut = jest.fn();
const mockDelete = jest.fn();

jest.mock('../api', () => ({
  __esModule: true,
  default: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
    put: (...args: any[]) => mockPut(...args),
    delete: (...args: any[]) => mockDelete(...args),
  },
}));

import {
  listCommunityPosts,
  publishDietRecordToCommunity,
  removeCommunityReaction,
  reportCommunityPost,
  setCommunityReaction,
} from '../community';

describe('community service', () => {
  beforeEach(() => jest.clearAllMocks());

  it('publishes an owned diet record with a stable idempotency key', async () => {
    mockPost.mockResolvedValueOnce({ data: { id: 7 } });

    await publishDietRecordToCommunity(91, '认真吃饭', 'diet-91-share-1');

    expect(mockPost).toHaveBeenCalledWith('/community/posts', {
      source_type: 'diet_record',
      source_id: 91,
      caption: '认真吃饭',
      idempotency_key: 'diet-91-share-1',
    });
  });

  it('loads a cursor feed and updates or removes one reaction', async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [] } });
    mockPut.mockResolvedValueOnce({ data: { id: 7, my_reaction: 'support' } });
    mockDelete.mockResolvedValueOnce({ data: { id: 7, my_reaction: null } });

    await listCommunityPosts({ limit: 20, beforeId: 50 });
    await setCommunityReaction(7, 'support');
    await removeCommunityReaction(7);

    expect(mockGet).toHaveBeenCalledWith('/community/posts', {
      params: { limit: 20, before_id: 50 },
    });
    expect(mockPut).toHaveBeenCalledWith('/community/posts/7/reaction', { reaction: 'support' });
    expect(mockDelete).toHaveBeenCalledWith('/community/posts/7/reaction');
  });

  it('reports a post without sending health context', async () => {
    mockPost.mockResolvedValueOnce({ data: { report_count: 1, status: 'active' } });

    await reportCommunityPost(8, '不适当内容');

    expect(mockPost).toHaveBeenCalledWith('/community/posts/8/report', { reason: '不适当内容' });
  });
});
