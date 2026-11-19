import { useLoaderData } from 'expo-router';

import { useApiQuery } from '@/hooks/use-api-query';
import type { loadPlans } from '@/lib/plans';
import type { Plan } from '@/lib/types';

/** From the route's loader (`loadPlans`), so they're in the server's page; fetched here when it couldn't. Loader routes only. */
export function usePlans() {
  const { plans } = useLoaderData<typeof loadPlans>();
  const query = useApiQuery<Plan[]>('/billing/plans/', { enabled: !plans });
  return plans ? { plans, error: null } : { plans: query.data, error: query.error };
}
