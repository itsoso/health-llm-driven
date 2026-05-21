import { useQuery } from '@tanstack/react-query';
import { getCaseDetail, type CaseDetail } from '../services/clinicalJournal';

export function useCaseDetail(caseId: number | null) {
  return useQuery<CaseDetail>({
    queryKey: ['clinicalJournal', 'case', caseId],
    queryFn: () => getCaseDetail(caseId as number),
    enabled: caseId !== null && caseId !== undefined,
    staleTime: 60_000,
  });
}
