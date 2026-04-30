import { useQuery } from '@tanstack/react-query';
import {
  listCases, getCaseDetail, recentEntries,
  type CaseSummary, type CaseDetail, type RecentEntry,
} from '../services/clinicalJournal';

export function useCaseList(status?: string) {
  return useQuery<CaseSummary[]>({
    queryKey: ['clinicalJournal', 'cases', status ?? 'all'],
    queryFn: () => listCases(status),
    staleTime: 60_000,
  });
}

export function useCaseDetail(caseId: number | null) {
  return useQuery<CaseDetail>({
    queryKey: ['clinicalJournal', 'case', caseId],
    queryFn: () => getCaseDetail(caseId as number),
    enabled: caseId !== null && caseId !== undefined,
    staleTime: 60_000,
  });
}

export function useRecentEntries(days: number = 14) {
  return useQuery<RecentEntry[]>({
    queryKey: ['clinicalJournal', 'recentEntries', days],
    queryFn: () => recentEntries(days),
    staleTime: 120_000,
  });
}
