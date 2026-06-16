/**
 * 引导式运动执行 React Query 封装(消费 /movement/guided-task)。
 *
 * useGuidedTask(domain) — 拉某个运动域的引导任务(门控 + 动作 + 计划 + 语音脚本)。
 *
 * 完成写回复用 useCompleteAgendaItem(若运动项带 complete_ref 走 /agenda/complete);
 * 没有 complete_ref 时,屏内用本地完成回调 + invalidate ['timeline','today'](见 guided-task 屏)。
 */
import { useQuery } from '@tanstack/react-query';
import { fetchGuidedTask } from '../services/guidedTask';

export { useCompleteAgendaItem } from './useTodayTimeline';

export function useGuidedTask(domain: string) {
  return useQuery({
    queryKey: ['guided-task', domain],
    queryFn: () => fetchGuidedTask(domain),
    staleTime: 60_000,
    enabled: Boolean(domain),
  });
}
