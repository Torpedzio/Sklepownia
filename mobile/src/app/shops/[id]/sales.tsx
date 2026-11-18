import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { Icon } from '@/components/icon';
import { Page } from '@/components/page';
import { PushPrompt } from '@/components/push-prompt';
import { SalesChart } from '@/components/sales-chart';
import { Badge } from '@/components/status-badge';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api } from '@/lib/api';
import { formatMoney } from '@/lib/format';
import { ORDER_STATUS_COLORS, ordersLabel, revenueChange, SALES_POLL_MS } from '@/lib/sales';
import { formatTime } from '@/lib/settings-form';
import type { SalesPeriod, ShopDetail, ShopOrder, ShopSales } from '@/lib/types';

export default function ShopSalesScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const theme = useTheme();
  const notify = useNotify();
  const { data: shop } = useApiQuery<ShopDetail>(`/shops/${id}/`);
  const {
    data: sales,
    error,
    refresh,
  } = useApiQuery<ShopSales>(`/shops/${id}/sales/`, {
    refetchInterval: (data) => (data?.refreshing ? SALES_POLL_MS : false),
  });
  const [asking, setAsking] = useState(false);

  async function readAgain() {
    setAsking(true);
    try {
      const result = await api<ShopSales>(`/shops/${id}/sales/refresh/`, { method: 'POST' });
      // Read a moment ago: the numbers on screen are current.
      if (!result.refreshing) notify.success('Zamówienia są aktualne, odczytaliśmy je przed chwilą.');
      await refresh();
    } catch (e) {
      notify.error((e as Error).message);
    } finally {
      setAsking(false);
    }
  }

  const header = (
    <>
      <Stack.Screen
        options={{
          title: 'Sprzedaż',
          ...backArrowOptions({ pathname: '/shops/[id]', params: { id } }, 'Wróć do sklepu'),
        }}
      />
      <View style={styles.header}>
        <ThemedText type="title">Sprzedaż</ThemedText>
        {shop ? (
          <ThemedText themeColor="textSecondary">
            {shop.name}, zamówienia z ostatnich 30 dni
          </ThemedText>
        ) : null}
      </View>
    </>
  );

  if (!sales) {
    return (
      <Page>
        {header}
        {error ? (
          <ThemedText themeColor="danger">{error.message}</ThemedText>
        ) : (
          <ActivityIndicator style={styles.loader} />
        )}
      </Page>
    );
  }

  if (!sales.available) {
    return (
      <Page>
        {header}
        <Notice
          title="Sklep teraz nie działa"
          text="Zamówienia odczytujemy tylko z działającego sklepu. Gdy znów zadziała, zobaczysz tu jego sprzedaż."
        />
      </Page>
    );
  }

  const neverRead = sales.synced_at === null;
  const empty = sales.last_30_days.orders === 0 && sales.recent.length === 0;
  const panelName = shop?.panel_name ?? 'panel sklepu';
  const inPanel = `w ${panelName.replace(/^panel\b/, 'panelu')}`;
  const toHandle = sales.to_handle.new + sales.to_handle.processing;

  return (
    <Page>
      {header}

      <View style={styles.status}>
        {sales.refreshing ? <ActivityIndicator size="small" /> : null}
        <ThemedText type="small" themeColor="textSecondary" style={styles.flex}>
          {sales.refreshing
            ? 'Odczytujemy zamówienia ze sklepu…'
            : sales.synced_at
              ? `Zamówienia odczytane ze sklepu ${formatTime(sales.synced_at)}.`
              : 'Zamówień jeszcze nie odczytaliśmy.'}
        </ThemedText>
        <Button
          title="Odśwież"
          icon="refresh"
          variant="secondary"
          loading={asking}
          disabled={sales.refreshing}
          onPress={readAgain}
        />
      </View>

      <PushPrompt />

      {sales.error ? (
        <View style={[styles.card, { backgroundColor: theme.accentMuted, borderColor: theme.accent }]}>
          <View style={styles.row}>
            <Icon name="warning" size={18} color="warning" />
            <ThemedText type="smallBold" style={styles.flex}>
              {sales.error}
            </ThemedText>
          </View>
          {!neverRead ? (
            <ThemedText type="small" themeColor="textSecondary">
              Poniżej jest stan z ostatniego udanego odczytu.
            </ThemedText>
          ) : null}
        </View>
      ) : null}

      {neverRead ? (
        sales.refreshing ? (
          <Notice title="Za chwilę zobaczysz sprzedaż" text="Pierwszy odczyt zamówień trwa zwykle kilka sekund." />
        ) : null
      ) : empty ? (
        <Notice
          title="Nie ma jeszcze zamówień"
          text="Pokażemy je tutaj kilka minut po tym, jak klienci je złożą. Możesz też odświeżyć ręcznie."
        />
      ) : (
        <View style={[styles.content, sales.refreshing && styles.dimmed]}>
          <View style={styles.tiles}>
            <StatTile label="Dziś" period={sales.today} currency={sales.currency} />
            <StatTile label="Ostatnie 7 dni" period={sales.last_7_days} currency={sales.currency} />
            <StatTile
              label="Ostatnie 30 dni"
              period={sales.last_30_days}
              currency={sales.currency}
              previous={sales.previous_30_days}
            />
          </View>

          <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
            <ThemedText type="heading">Do obsłużenia</ThemedText>
            {toHandle ? (
              <>
                <View style={styles.handleRow}>
                  <Count value={sales.to_handle.new} label="Nowe" note="czekają na płatność albo potwierdzenie" />
                  <Count value={sales.to_handle.processing} label="W realizacji" note="opłacone, do wysłania" />
                </View>
                <ThemedText type="small" themeColor="textSecondary">
                  Zamówienia obsłużysz {inPanel}.
                </ThemedText>
                <Button
                  title={panelName.charAt(0).toUpperCase() + panelName.slice(1)}
                  icon="admin"
                  variant="secondary"
                  style={styles.start}
                  onPress={() =>
                    router.push({ pathname: '/shops/[id]/settings', params: { id: String(id), section: 'reczne' } })
                  }
                />
              </>
            ) : (
              <ThemedText type="small" themeColor="textSecondary">
                Wszystkie zamówienia są obsłużone.
              </ThemedText>
            )}
          </View>

          <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
            <SalesChart days={sales.daily} currency={sales.currency} />
          </View>

          {sales.recent.length ? (
            <View style={styles.section}>
              <ThemedText type="heading">Ostatnie zamówienia</ThemedText>
              <View style={[styles.list, { backgroundColor: theme.surface, borderColor: theme.border }]}>
                {sales.recent.map((order, index) => (
                  <OrderRow key={`${order.number}-${order.placed_at}`} order={order} first={index === 0} />
                ))}
              </View>
            </View>
          ) : null}

          <ThemedText type="small" themeColor="textSecondary">
            Sumy obejmują zamówienia w walucie sklepu ({sales.currency}), bez anulowanych i bez tych z niedokończoną
            płatnością. Z danych klienta pokazujemy tu tylko imię i inicjał. Resztę znajdziesz {inPanel}.
          </ThemedText>
        </View>
      )}
    </Page>
  );
}

function StatTile({
  label,
  period,
  currency,
  previous,
}: {
  label: string;
  period: SalesPeriod;
  currency: string;
  previous?: SalesPeriod;
}) {
  const theme = useTheme();
  const change = previous ? revenueChange(period, previous) : null;
  const tone = change?.direction === 'up' ? 'success' : change?.direction === 'down' ? 'danger' : 'textSecondary';

  return (
    <View style={[styles.tile, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <ThemedText type="small" themeColor="textSecondary">
        {label}
      </ThemedText>
      <ThemedText type="subtitle" style={styles.digits}>
        {formatMoney(period.revenue, currency)}
      </ThemedText>
      <ThemedText type="small" themeColor="textSecondary">
        {period.orders
          ? `${ordersLabel(period.orders)}, średnio ${formatMoney(period.average, currency)}`
          : 'Bez zamówień'}
      </ThemedText>
      {change ? (
        <View style={styles.row}>
          {change.direction !== 'same' ? (
            <Icon name={change.direction === 'up' ? 'arrowUp' : 'arrowDown'} size={14} color={tone} />
          ) : null}
          <ThemedText type="smallBold" themeColor={tone} style={styles.flex}>
            {change.text}
          </ThemedText>
        </View>
      ) : null}
    </View>
  );
}

function Count({ value, label, note }: { value: number; label: string; note: string }) {
  return (
    <View style={styles.count}>
      <ThemedText type="subtitle" style={styles.digits}>
        {value}
      </ThemedText>
      <View style={styles.flex}>
        <ThemedText type="smallBold">{label}</ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          {note}
        </ThemedText>
      </View>
    </View>
  );
}

function OrderRow({ order, first }: { order: ShopOrder; first: boolean }) {
  const theme = useTheme();
  const [color, background] = ORDER_STATUS_COLORS[order.status];
  const details = [order.customer, `${order.items} szt.`, formatTime(order.placed_at)].filter(Boolean).join(', ');

  return (
    <View style={[styles.order, !first && { borderTopColor: theme.border, borderTopWidth: StyleSheet.hairlineWidth }]}>
      <View style={styles.flex}>
        <ThemedText type="smallBold">Nr {order.number}</ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          {details}
        </ThemedText>
      </View>
      <View style={styles.orderEnd}>
        <ThemedText type="smallBold" style={styles.digits}>
          {formatMoney(order.total, order.currency)}
        </ThemedText>
        <Badge label={order.status_display} color={color} background={background} />
      </View>
    </View>
  );
}

function Notice({ title, text }: { title: string; text: string }) {
  const theme = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <ThemedText type="heading">{title}</ThemedText>
      <ThemedText type="small" themeColor="textSecondary">
        {text}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  loader: {
    marginVertical: Spacing.six,
  },
  header: {
    gap: Spacing.one,
  },
  status: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: Spacing.two,
  },
  content: {
    gap: Spacing.four,
  },
  // Last read's numbers stay on screen while the next read runs.
  dimmed: {
    opacity: 0.6,
  },
  tiles: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
  tile: {
    flexGrow: 1,
    flexBasis: 200,
    gap: Spacing.one,
    padding: Spacing.three,
    borderRadius: Radius.medium,
    borderWidth: 1,
  },
  digits: {
    fontVariant: ['tabular-nums'],
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.one,
  },
  card: {
    gap: Spacing.two,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  handleRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.four,
  },
  count: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    flexGrow: 1,
    flexBasis: 220,
  },
  start: {
    alignSelf: 'flex-start',
  },
  section: {
    gap: Spacing.three,
  },
  list: {
    borderRadius: Radius.large,
    borderWidth: 1,
    paddingHorizontal: Spacing.three,
  },
  order: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
    paddingVertical: Spacing.three,
  },
  orderEnd: {
    alignItems: 'flex-end',
    gap: Spacing.one,
  },
});
