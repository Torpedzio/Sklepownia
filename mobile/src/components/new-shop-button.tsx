import { Link } from 'expo-router';

import { Button, type ButtonProps } from '@/components/ui/button';
import { Tooltip, type TooltipProps } from '@/components/ui/tooltip';
import { useAuth } from '@/context/auth';
import { plural } from '@/lib/plural';

export function shopLimitMessage(limit: number) {
  return `Osiągnięto limit ${limit} ${plural(limit, ['sklepu', 'sklepów', 'sklepów'])} na konto. Usuń jeden ze sklepów, żeby założyć nowy.`;
}

export function isShopLimitReached(limit: number | undefined, shopCount: number | undefined) {
  return limit !== undefined && shopCount !== undefined && shopCount >= limit;
}

type NewShopButtonProps = Omit<ButtonProps, 'onPress' | 'disabled'> & {
  /** The user's live shops; until they load, the button stays usable and the server enforces the limit. */
  shopCount: number | undefined;
  tooltipSide?: TooltipProps['side'];
};

export function NewShopButton({ shopCount, tooltipSide, ...buttonProps }: NewShopButtonProps) {
  const { user } = useAuth();
  const limit = user?.shop_limit;

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
