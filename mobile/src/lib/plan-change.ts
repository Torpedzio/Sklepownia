import type { Plan, ShopBrief } from '@/lib/types';

/**
 * Keeps or suspends shop `id`. Keeping one more when the plan is full swaps it for the shop kept longest
 * (a Magento shop for a Magento shop, when Magento is what is full), so the owner never has to untick first.
 */
export function toggleKept(
  shops: ShopBrief[],
  kept: number[],
  id: number,
  plan: Pick<Plan, 'name' | 'max_shops' | 'max_magento_shops'>,
): { keep: number[] } | { error: string } {
  if (kept.includes(id)) return { keep: kept.filter((shopId) => shopId !== id) };
  const isMagento = (shopId: number) => shops.find((shop) => shop.id === shopId)?.platform === 'magento';
  if (isMagento(id) && !plan.max_magento_shops) {
    return { error: `Plan ${plan.name} nie obejmuje sklepów Magento.` };
  }
  if (!plan.max_shops) return { error: `Plan ${plan.name} nie obejmuje sklepów.` };
  let next = [...kept, id];
  if (isMagento(id) && next.filter(isMagento).length > plan.max_magento_shops) {
    const oldest = next.find(isMagento);
    next = next.filter((shopId) => shopId !== oldest);
  }
  if (next.length > plan.max_shops) next = next.slice(next.length - plan.max_shops);
  return { keep: next };
}
