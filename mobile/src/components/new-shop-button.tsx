import { Link } from 'expo-router';

import { Button, type ButtonProps } from '@/components/ui/button';
import { Tooltip, type TooltipProps } from '@/components/ui/tooltip';
import { useAuth } from '@/context/auth';
import { plural } from '@/lib/plural';
import type { Shop } from '@/lib/types';

export function shopLimitMessage(limit: number) {
  return `Twój plan pozwala na ${limit} ${plural(limit, ['sklep', 'sklepy', 'sklepów'])}. Usuń jeden ze sklepów, żeby założyć nowy.`;
}

export function isShopLimitReached(limit: number | undefined, shopCount: number | undefined) {
  return limit !== undefined && shopCount !== undefined && shopCount >= limit;
}

/** Shops that count towards the plan: test shops from before paid plans don't. */
export function paidShopCount(shops: Shop[] | undefined) {
  return shops?.filter((shop) => !shop.is_test).length;
}

type NewShopButtonProps = Omit<ButtonProps, 'onPress' | 'disabled'> & {
  /** The user's live shops that count towards the plan; until they load, the server enforces the limit. */
  shopCount: number | undefined;
  tooltipSide?: TooltipProps['side'];
};

/** Opens the new shop form; without a plan it leads to choosing one, at the plan's limit it explains why not. */
export function NewShopButton({ shopCount, tooltipSide, ...buttonProps }: NewShopButtonProps) {
  const { user } = useAuth();
  const limit = user?.shop_limit;

  if (user && !user.plan) {
    return (
      <Link href="/billing/checkout" asChild>
        <Button {...buttonProps} />
      </Link>
    );
  }
  if (limit !== undefined && isShopLimitReached(limit, shopCount)) {
    return (
      <Tooltip
        text={shopLimitMessage(limit)}
        accessibilityLabel={`${buttonProps.title}, niedostępne`}
        side={tooltipSide}>
        <Button {...buttonProps} disabled />
      </Tooltip>
    );
  }
  return (
    <Link href="/shops/new" asChild>
      <Button {...buttonProps} />
    </Link>
  );
}
