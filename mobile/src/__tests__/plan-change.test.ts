import { toggleKept } from '@/lib/plan-change';
import type { ShopBrief } from '@/lib/types';

const shop = (id: number, platform: ShopBrief['platform'] = 'woocommerce'): ShopBrief => ({
  id,
  name: `Sklep ${id}`,
  status: 'active',
  platform,
  platform_display: platform,
});
const shops = [shop(1, 'magento'), shop(2), shop(3), shop(4, 'magento')];
const standard = { name: 'Standard', max_shops: 3, max_magento_shops: 1 };
const start = { name: 'Start', max_shops: 1, max_magento_shops: 0 };

test('unticking just drops the shop', () => {
  expect(toggleKept(shops, [1, 2, 3], 2, standard)).toEqual({ keep: [1, 3] });
});

test('with room, the shop is added', () => {
  expect(toggleKept(shops, [1, 2], 3, standard)).toEqual({ keep: [1, 2, 3] });
});

test('when the plan is full, the shop kept longest makes room', () => {
  expect(toggleKept(shops, [2, 3], 1, { ...standard, max_shops: 2 })).toEqual({ keep: [3, 1] });
});

test('when Magento is full, a Magento shop makes room', () => {
  expect(toggleKept(shops, [1, 2, 3], 4, standard)).toEqual({ keep: [2, 3, 4] });
});

test('a plan without Magento says so', () => {
  expect(toggleKept(shops, [2], 1, start)).toEqual({ error: 'Plan Start nie obejmuje sklepów Magento.' });
});
