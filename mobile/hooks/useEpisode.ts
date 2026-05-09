/**
 * Episode hooks — Agent-Native v3 Increment 2.
 *
 * 三个 hook:
 *   useMyEpisodes    最近 Episode 列表 (Home / Record tab 用)
 *   useEpisode       单个 Episode 详情 (详情页用)
 *   useEpisodeFeedback  提交反馈 + 自动失效列表/详情缓存
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  listMyEpisodes,
  getEpisode,
  submitEpisodeFeedback,
  type EpisodeListItem,
  type EpisodeDetail,
  type EpisodeStatus,
  type FeedbackPayload,
} from '../services/episodes';
import { queryKeys } from '../applib/queryKeys';

export function useMyEpisodes(params?: {
  days?: number;
  limit?: number;
  episode_type?: string;
  status?: EpisodeStatus;
  enabled?: boolean;
}) {
  const { enabled = true, ...query } = params || {};
  return useQuery<EpisodeListItem[]>({
    queryKey: [...queryKeys.episodesRoot, 'me', query],
    queryFn: () => listMyEpisodes(query),
    staleTime: 60_000,
    enabled,
  });
}

export function useEpisode(id: number | null | undefined) {
  return useQuery<EpisodeDetail>({
    queryKey: [...queryKeys.episodesRoot, 'detail', id],
    queryFn: () => getEpisode(id as number),
    enabled: typeof id === 'number' && id > 0,
    staleTime: 30_000,
  });
}

export function useEpisodeFeedback(episodeId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: FeedbackPayload) =>
      submitEpisodeFeedback(episodeId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [...queryKeys.episodesRoot, 'detail', episodeId] });
      qc.invalidateQueries({ queryKey: [...queryKeys.episodesRoot, 'me'] });
    },
  });
}
