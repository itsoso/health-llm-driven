import api from './client';

export interface ActivityCategoryStats {
  category: string;
  total_minutes: number;
  count: number;
  percentage: number;
}

export interface ActivityStatsData {
  total_records: number;
  total_active_minutes: number;
  category_distribution: ActivityCategoryStats[];
}

export interface ActivityStatusData {
  id: number;
  user_id: number;
  status_text: string;
  category: string;
  start_time: string;
  estimated_duration_minutes: number | null;
  estimated_end_time: string | null;
  actual_end_time: string | null;
  is_active: boolean;
  notes: string | null;
  created_at: string;
}

export interface ActivityTimelineItem {
  id: number;
  status_text: string;
  category: string;
  start_time: string;
  end_time: string | null;
  duration_minutes: number | null;
  is_active: boolean;
}

export interface DMConversationItem {
  friend_id: number;
  friend_name: string;
  friend_avatar: string | null;
  last_message: string;
  last_message_time: string;
  unread_count: number;
}

export interface DMHistoryResponse {
  messages: DMResponse[];
  has_more: boolean;
}

export interface DMResponse {
  id: number;
  sender_id: number;
  receiver_id: number;
  content: string;
  is_read: boolean;
  created_at: string;
  sender_name: string | null;
  sender_avatar: string | null;
}

export interface DailyPointsData {
  date: string;
  total_points: number;
  items: PointItemData[];
}

export interface FriendInfo {
  user_id: number;
  name: string;
  avatar_url: string | null;
  friendship_id: number;
  since: string;
}

export interface FriendRequestData {
  id: number;
  user_id: number;
  friend_id: number;
  status: string;
  message: string | null;
  created_at: string;
  user_name: string | null;
  user_avatar: string | null;
  friend_name: string | null;
  friend_avatar: string | null;
}

export interface GroupDetail {
  id: number;
  name: string;
  avatar_url: string | null;
  creator_id: number;
  members: GroupMemberInfo[];
  created_at: string;
}

export interface GroupListItem {
  id: number;
  name: string;
  avatar_url: string | null;
  member_count: number;
  last_message: string | null;
  last_message_at: string | null;
  created_at: string;
}

export interface GroupMemberInfo {
  user_id: number;
  name: string;
  avatar_url: string | null;
  role: string;
  joined_at: string;
}

export interface GroupMsgData {
  id: number;
  group_id: number;
  sender_id: number;
  sender_name: string;
  sender_avatar: string | null;
  content: string;
  created_at: string;
}

export interface GroupMsgHistory {
  messages: GroupMsgData[];
  has_more: boolean;
}

export interface PKChallengeData {
  id: number;
  creator_id: number;
  creator_name: string | null;
  title: string;
  challenge_type: string;
  checkin_template_id: number | null;
  checkin_template_name: string | null;
  activity_category: string | null;
  metric: string;
  duration_days: number;
  start_date: string;
  end_date: string;
  status: string;
  participants: ParticipantInfoData[];
  created_at: string;
}

export interface PKChallengeDetailData extends PKChallengeData {
  leaderboard: ParticipantInfoData[];
}

export interface PKStatsData {
  total_challenges: number;
  wins: number;
  active_challenges: number;
  total_points: number;
}

// ===== 每日健康积分 =====

export interface ParticipantInfoData {
  user_id: number;
  user_name: string;
  user_avatar: string | null;
  score: number;
  rank: number | null;
  points: number;
  joined_at: string;
}

export interface PointItemData {
  category: string;
  name: string;
  points: number;
  max_points: number;
  detail: string;
}

export interface PointsHistoryItemData {
  date: string;
  total_points: number;
}

export interface PointsSummaryData {
  today_points: number;
  week_points: number;
  month_points: number;
  streak_days: number;
  today_detail: DailyPointsData;
}

export interface UserSearchResultData {
  id: number;
  name: string;
  avatar_url: string | null;
  is_friend: boolean;
  request_pending: boolean;
}

export const friendsApi = {
  sendRequest: (friendId: number, message?: string) =>
    api.post<FriendRequestData>('/friends/request', { friend_id: friendId, message }),
  acceptRequest: (requestId: number) =>
    api.put<FriendRequestData>(`/friends/request/${requestId}/accept`),
  rejectRequest: (requestId: number) =>
    api.put<FriendRequestData>(`/friends/request/${requestId}/reject`),
  listFriends: () =>
    api.get<FriendInfo[]>('/friends/list'),
  pendingRequests: () =>
    api.get<FriendRequestData[]>('/friends/requests/pending'),
  removeFriend: (friendshipId: number) =>
    api.delete(`/friends/${friendshipId}`),
  searchUsers: (q: string) =>
    api.get<UserSearchResultData[]>(`/friends/search?q=${encodeURIComponent(q)}`),
};

// ===== PK挑战 =====

export const dmApi = {
  getConversations: () =>
    api.get<DMConversationItem[]>('/dm/conversations'),
  getMessages: (friendId: number, beforeId?: number, limit?: number) =>
    api.get<DMHistoryResponse>(`/dm/messages/${friendId}`, {
      params: { before_id: beforeId || 0, limit: limit || 30 },
    }),
  sendMessage: (receiverId: number, content: string) =>
    api.post<DMResponse>('/dm/send', { receiver_id: receiverId, content }),
  markRead: (friendId: number) =>
    api.put(`/dm/read/${friendId}`),
  getUnreadCount: () =>
    api.get<{ total_unread: number }>('/dm/unread-count'),
};

// 排泄记录 API
export const groupApi = {
  create: (name: string, memberIds: number[]) =>
    api.post<GroupDetail>('/groups', { name, member_ids: memberIds }),
  list: () =>
    api.get<GroupListItem[]>('/groups'),
  getDetail: (groupId: number) =>
    api.get<GroupDetail>(`/groups/${groupId}`),
  update: (groupId: number, name: string) =>
    api.put<GroupDetail>(`/groups/${groupId}`, { name }),
  dissolve: (groupId: number) =>
    api.delete(`/groups/${groupId}`),
  sendMessage: (groupId: number, content: string) =>
    api.post<GroupMsgData>(`/groups/${groupId}/messages`, { content }),
  getMessages: (groupId: number, beforeId?: number, limit?: number) =>
    api.get<GroupMsgHistory>(`/groups/${groupId}/messages`, {
      params: { before_id: beforeId || 0, limit: limit || 50 },
    }),
  addMember: (groupId: number, userId: number) =>
    api.post(`/groups/${groupId}/members`, { user_id: userId }),
  removeMember: (groupId: number, userId: number) =>
    api.delete(`/groups/${groupId}/members/${userId}`),
  leave: (groupId: number) =>
    api.post(`/groups/${groupId}/leave`),
};

export const pkChallengeApi = {
  create: (data: {
    title: string;
    challenge_type: string;
    checkin_template_id?: number;
    activity_category?: string;
    metric?: string;
    duration_days?: number;
    duration_minutes?: number;
    friend_ids: number[];
  }) => api.post<PKChallengeData>('/pk-challenges', data),
  list: (status?: string) =>
    api.get<PKChallengeData[]>('/pk-challenges', { params: status ? { status } : {} }),
  getDetail: (id: number) =>
    api.get<PKChallengeDetailData>(`/pk-challenges/${id}`),
  refresh: (id: number) =>
    api.post<PKChallengeDetailData>(`/pk-challenges/${id}/refresh`),
  cancel: (id: number) =>
    api.delete(`/pk-challenges/${id}`),
  myStats: () =>
    api.get<PKStatsData>('/pk-challenges/stats/me'),
};

// ====== 单词本 ======
export const dailyPointsApi = {
  getToday: () =>
    api.get<DailyPointsData>('/points/today'),
  getDate: (targetDate: string) =>
    api.get<DailyPointsData>(`/points/date/${targetDate}`),
  getSummary: () =>
    api.get<PointsSummaryData>('/points/summary'),
  getHistory: (days: number = 7) =>
    api.get<PointsHistoryItemData[]>(`/points/history?days=${days}`),
};

export const activityStatusApi = {
  createRecord: (data: { status_text: string; category: string; estimated_duration_minutes?: number; notes?: string }) =>
    api.post<ActivityStatusData>('/activity-status/records', data),
  getCurrentStatus: () =>
    api.get<ActivityStatusData | null>('/activity-status/records/me/current'),
  endRecord: (recordId: number) =>
    api.put<ActivityStatusData>(`/activity-status/records/${recordId}/end`),
  getTodayTimeline: () =>
    api.get<ActivityTimelineItem[]>('/activity-status/records/me/today'),
  getMyRecords: (params?: { start_date?: string; end_date?: string; limit?: number }) =>
    api.get<ActivityStatusData[]>('/activity-status/records/me', { params }),
  getRecord: (recordId: number) =>
    api.get<ActivityStatusData>(`/activity-status/records/${recordId}`),
  deleteRecord: (recordId: number) =>
    api.delete(`/activity-status/records/${recordId}`),
  getStats: (days: number = 7) =>
    api.get<ActivityStatsData>(`/activity-status/stats/me?days=${days}`),
};

// ===== 好友关系 =====
