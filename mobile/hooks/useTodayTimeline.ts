/**
 * 今日时间线 React Query 封装(消费 /timeline/today)。
 *
 * useTodayTimeline       — 拉今日时间线快照。
 * useCompleteTimelineItem — 完成一条 action(复用 /agenda/complete 双轨),
 *                           成功后 invalidate ['timeline','today'] + ['agenda','today']。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { completeAgendaItem, type AgendaSource } from '../services/agenda';
import { fetchTodayTimeline } from '../services/todayTimeline';

const TIMELINE_TODAY_KEY = ['timeline', 'today'];
const AGENDA_TODAY_KEY = ['agenda', 'today'];

export function useTodayTimeline() {
  return useQuery({
    queryKey: TIMELINE_TODAY_KEY,
    queryFn: fetchTodayTimeline,
    staleTime: 60_000,
  });
}

/** 完成一条时间线 action —— 走协议轨,写真实业务记录。失败会 throw,调用方需给反馈。 */
export function useCompleteAgendaItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (source: AgendaSource) => completeAgendaItem(source, 'protocol'),
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: TIMELINE_TODAY_KEY }),
        qc.invalidateQueries({ queryKey: AGENDA_TODAY_KEY }),
      ]),
  });
}
