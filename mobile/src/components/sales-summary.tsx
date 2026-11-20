import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing } from '@/constants/theme';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { formatMoney } from '@/lib/format';
import { plural } from '@/lib/plural';
import { ordersLabel, SALES_POLL_MS } from '@/lib/sales';
import type { ShopSales } from '@/lib/types';

export function SalesSummary({ shopId }: { shopId: number }) {
  const theme = useTheme();
  const { data: sales } = useApiQuery<ShopSales>(`/shops/${shopId}/sales/`, {
    refetchInterval: (data) => (data?.refreshing ? SALES_POLL_MS : false),
  });
  // Without the numbers the card has nothing to say; the shop's screen works without it.
  if (!sales?.available) return null;

  const toHandle = sales.to_handle.new + sales.to_handle.processing;

  return (
    <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <ThemedText type="heading">Sprzedaż</ThemedText>
      {sales.synced_at === null ? (
        <ThemedText type="small" themeColor="textSecondary">
          {sales.refreshing ? 'Odczytujemy zamówienia ze sklepu…' : sales.error || 'Zamówień jeszcze nie odczytaliśmy.'}
        </ThemedText>
      ) : (
        <View style={styles.figures}>
          <Figure
            label="Dziś"
            value={formatMoney(sales.today.revenue, sales.currency)}
            note={ordersLabel(sales.today.orders)}
          />
          <Figure
            label="Ostatnie 30 dni"
            value={formatMoney(sales.last_30_days.revenue, sales.currency)}
            note={ordersLabel(sales.last_30_days.orders)}
          />
          <Figure
            label="Do obsłużenia"
            value={String(toHandle)}
            note={plural(toHandle, ['zamówienie', 'zamówienia', 'zamówień'])}
          />
        </View>
      )}
      <View style={styles.actions}>
        <Button
          title="Zobacz sprzedaż"
          icon="chart"
          variant="secondary"
          onPress={() => router.push({ pathname: '/shops/[id]/sales', params: { id: String(shopId) } })}
        />
        <Button
          title="Zamówienia"
          icon="cart"
          variant="secondary"
          onPress={() => router.push({ pathname: '/shops/[id]/orders', params: { id: String(shopId) } })}
        />
      </View>
    </View>
  );
}

function Figure({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <View style={styles.figure}>
      <ThemedText type="small" themeColor="textSecondary">
        {label}
      </ThemedText>
      <ThemedText type="subtitle" style={styles.digits}>
        {value}
      </ThemedText>
      <ThemedText type="small" themeColor="textSecondary">
        {note}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  figures: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.four,
  },
  figure: {
    flexGrow: 1,
    flexBasis: 140,
  },
  digits: {
    fontVariant: ['tabular-nums'],
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
  },
});
