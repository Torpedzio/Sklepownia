import { useLoaderData } from 'expo-router';

import { useApiQuery } from '@/hooks/use-api-query';
import type { loadPlans } from '@/lib/plans';
import type { Plan } from '@/lib/types';

/**
 * The plans on offer, from the route's loader (`loadPlans`): the server puts them in the page. When it couldn't
 * get them, the page asks the platform itself. Only for routes exporting that loader.
 */
export function usePlans() {
  const { plans } = useLoaderData<typeof loadPlans>();
  const query = useApiQuery<Plan[]>('/billing/plans/', { enabled: !plans });
  return plans ? { plans, error: null } : { plans: query.data, error: query.error };
}
