/* eslint-disable import/first */
import React from 'react';
import { fireEvent, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockList = jest.fn();
const mockPublish = jest.fn();
const mockSetReaction = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack }),
  useLocalSearchParams: () => ({ composeRecordId: '91' }),
}));

jest.mock('../../services/community', () => ({
  listCommunityPosts: (...args: any[]) => mockList(...args),
  publishDietRecordToCommunity: (...args: any[]) => mockPublish(...args),
  setCommunityReaction: (...args: any[]) => mockSetReaction(...args),
  removeCommunityReaction: jest.fn(),
  deleteCommunityPost: jest.fn(),
  reportCommunityPost: jest.fn(),
}));

import CommunityScreen from '../community';
import { renderWithProviders } from '../../test-utils';

const peerPost = {
  id: 8,
  anonymous_name: '同行者',
  source_type: 'diet_record',
  snapshot: {
    meal_type: 'lunch',
    record_date: '2026-07-25',
    food_items: '三文鱼、糙米、西兰花',
    calories: 620,
    protein: 42,
    carbs: 58,
    fat: 22,
    fiber: 8,
  },
  caption: '今天也认真吃饭了',
  status: 'active',
  reaction_counts: { support: 2, same_path: 1, learned: 0 },
  my_reaction: null,
  is_owner: false,
  created_at: '2026-07-25T12:00:00Z',
};

describe('CommunityScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockList.mockResolvedValue([peerPost]);
    mockPublish.mockResolvedValue({ ...peerPost, id: 9, is_owner: true });
    mockSetReaction.mockResolvedValue({
      ...peerPost,
      my_reaction: 'support',
      reaction_counts: { support: 3, same_path: 1, learned: 0 },
    });
  });

  it('requires explicit confirmation and describes the privacy projection', async () => {
    const screen = renderWithProviders(<CommunityScreen />);

    expect(screen.getByText('发布这次饮食记录？')).toBeTruthy();
    expect(screen.getByText('仅分享餐次、食物与营养摘要。照片、体重和健康档案不会公开。')).toBeTruthy();
    expect(screen.getByText('请勿填写姓名、病史、用药或联系方式。')).toBeTruthy();

    fireEvent.press(screen.getByLabelText('确认发布到同行圈'));

    await waitFor(() => expect(mockPublish).toHaveBeenCalledWith(
      91,
      '',
      expect.stringMatching(/^community-diet-91-/),
    ));
    expect(screen.queryByText('发布这次饮食记录？')).toBeNull();
  });

  it('loads peer posts and updates a support reaction in place', async () => {
    const screen = renderWithProviders(<CommunityScreen />);

    await waitFor(() => expect(screen.getByText('三文鱼、糙米、西兰花')).toBeTruthy());
    fireEvent.press(screen.getByLabelText('支持 2'));

    await waitFor(() => expect(mockSetReaction).toHaveBeenCalledWith(8, 'support'));
    expect(screen.getByLabelText('支持 3')).toBeTruthy();
  });

  it('keeps the private receipt safe and allows retry after publish failure', async () => {
    mockPublish.mockRejectedValueOnce(new Error('network'));
    const screen = renderWithProviders(<CommunityScreen />);

    fireEvent.press(screen.getByLabelText('确认发布到同行圈'));

    await waitFor(() => {
      expect(screen.getByText('发布失败，饮食记录未受影响。')).toBeTruthy();
      expect(screen.getByText('重试发布')).toBeTruthy();
    });
  });
});
