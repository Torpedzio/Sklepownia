import { API_URL } from '@/lib/api';
import type { Plan } from '@/lib/types';

export type PlansData = { plans: Plan[] | null };

/**
 * Route loader of the pages showing the plans: on the web the server fetches them while drawing the page, so the
 * prices are in it. Null when the platform doesn't answer in time; the page then fetches them itself.
 */
export async function loadPlans(): Promise<PlansData> {
  try {
    const response = await fetch(`${API_URL}/billing/plans/`, { signal: AbortSignal.timeout(3000) });
    return { plans: response.ok ? await response.json() : null };
  } catch {
    return { plans: null };
  }
}
