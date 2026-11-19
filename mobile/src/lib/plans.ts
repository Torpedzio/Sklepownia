import { API_URL } from '@/lib/api';
import type { Plan } from '@/lib/types';

export type PlansData = { plans: Plan[] | null };

/** On the web the server fetches the plans while rendering, so prices are in the page. Null on timeout: the page fetches. */
export async function loadPlans(): Promise<PlansData> {
  try {
    const response = await fetch(`${API_URL}/billing/plans/`, { signal: AbortSignal.timeout(3000) });
    return { plans: response.ok ? await response.json() : null };
  } catch {
    return { plans: null };
  }
}
