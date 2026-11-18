import { useApiQuery } from '@/hooks/use-api-query';
import type { Plan } from '@/lib/types';

/** The plans on offer. The web version takes them from the page's loader (lib/plans.ts). */
export function usePlans() {
  const { data, error } = useApiQuery<Plan[]>('/billing/plans/');
  return { plans: data, error };
}
