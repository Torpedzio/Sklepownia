import { router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { Icon } from '@/components/icon';
import { Badge } from '@/components/status-badge';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { formatMoney } from '@/lib/format';
import { ORDER_STATUS_COLORS } from '@/lib/sales';
import { formatTime } from '@/lib/settings-form';
import type { ShopOrder } from '@/lib/types';

/** An order in a list; opens its details, read from the shop. */
export function OrderRow({ shopId, order, first }: { shopId: number | string; order: ShopOrder; first: boolean }) {
  const theme = useTheme();
  const [color, background] = ORDER_STATUS_COLORS[order.status];
  const details = [order.customer, `${order.items} szt.`, formatTime(order.placed_at)].filter(Boolean).join(', ');
  const total = formatMoney(order.total, order.currency);

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Zamówienie nr ${order.number}, ${order.status_display}, ${total}`}
      onPress={() =>
        router.push({
          pathname: '/shops/[id]/orders/[orderId]',
          params: { id: String(shopId), orderId: order.external_id },
        })
      }
      style={({ pressed }) => [
        styles.row,
        !first && { borderTopColor: theme.border, borderTopWidth: StyleSheet.hairlineWidth },
        pressed && styles.pressed,
      ]}>
      <View style={styles.flex}>
        <ThemedText type="smallBold">Nr {order.number}</ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          {details}
        </ThemedText>
      </View>
      <View style={styles.end}>
        <ThemedText type="smallBold" style={styles.digits}>
          {total}
        </ThemedText>
        <Badge label={order.status_display} color={color} background={background} />
      </View>
      <Icon name="chevron" size={16} color="textSecondary" />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
    paddingVertical: Spacing.three,
  },
  pressed: {
    opacity: 0.6,
  },
  flex: {
    flex: 1,
  },
  end: {
    alignItems: 'flex-end',
    gap: Spacing.one,
  },
  digits: {
    fontVariant: ['tabular-nums'],
  },
});
