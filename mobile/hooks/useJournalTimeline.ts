import { useQuery } from '@tanstack/react-query';
import { fetchJournalTimeline, type TimelineThread } from '../services/clinicalJournal';

export function useJournalTimeline(days = 30) {
  return useQuery<{ threads: TimelineThread[] }>({
    queryKey: ['journal-timeline', days],
    queryFn: () => fetchJournalTimeline(days),
    staleTime: 60_000, // 1 min
  });
}
