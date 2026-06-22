/**
 * 今日时间线 React Query 封装(消费 /timeline/today)。
 *
 * useTodayTimeline       — 拉今日时间线快照。
 * useCompleteAgendaItem  — 完成一条 action(复用 /agenda/complete 双轨),
 *                          成功后 invalidate ['timeline','today'] + ['agenda','today']。
 * useSkipAgendaItem      — 跳过一条 action(R14,带可选失败原因),同一对失效收口。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  completeAgendaItem,
  type AgendaSkipReason,
  type AgendaSource,
} from '../services/agenda';
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

/** 完成 / 跳过共用的首页缓存失效:两个 key 一起,熄灭已处理的项。 */
function invalidateHomeTimeline(qc: ReturnType<typeof useQueryClient>) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: TIMELINE_TODAY_KEY }),
    qc.invalidateQueries({ queryKey: AGENDA_TODAY_KEY }),
  ]);
}

/** 完成一条时间线 action —— 走协议轨,写真实业务记录。失败会 throw,调用方需给反馈。 */
export function useCompleteAgendaItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (source: AgendaSource) => completeAgendaItem(source, 'protocol'),
    onSuccess: () => invalidateHomeTimeline(qc),
  });
}

export interface SkipAgendaInput {
  source: AgendaSource;
  /** 省略 = 不带原因(走 service 的默认兜底);带上 = R14 学习闭环原因。 */
  skipReason?: AgendaSkipReason;
}

/**
 * 跳过一条时间线 action(R14)—— 记录「没做 + 为什么」,经 /agenda/complete 写依从事实。
 * 失败会 throw,调用方需给反馈(与完成路径一致)。成功后失效首页两个 query key。
 */
export function useSkipAgendaItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ source, skipReason }: SkipAgendaInput) =>
      completeAgendaItem(source, 'protocol', undefined, {
        status: 'skipped',
        skipReason,
      }),
    onSuccess: () => invalidateHomeTimeline(qc),
  });
}
