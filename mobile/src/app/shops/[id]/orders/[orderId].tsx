import { Stack, useLocalSearchParams } from 'expo-router';
import type { ReactNode } from 'react';
import { ActivityIndicator, Linking, RefreshControl, StyleSheet, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { OrderActions } from '@/components/order-actions';
import { OrderNotes } from '@/components/order-notes';
import { Page } from '@/components/page';
import { Badge } from '@/components/status-badge';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { formatMoney } from '@/lib/format';
import { writeQuery } from '@/lib/query-cache';
import { ORDER_STATUS_COLORS } from '@/lib/sales';
import { formatTime } from '@/lib/settings-form';
import type { OrderAddress, ShopDetail, ShopOrderDetail } from '@/lib/types';

/** One order as the shop has it now, with the customer's contact data and addresses. */
export default function ShopOrderScreen() {
  const { id, orderId } = useLocalSearchParams<{ id: string; orderId: string }>();
  const theme = useTheme();
  const notify = useNotify();
  const { data: shop } = useApiQuery<ShopDetail>(`/shops/${id}/`);
  const path = `/shops/${id}/orders/${orderId}/`;
  const { data: order, error, isRefreshing, refresh } = useApiQuery<ShopOrderDetail>(path);

  const header = (
    <Stack.Screen
      options={{
        title: order ? `Zamówienie ${order.number}` : 'Zamówienie',
        ...backArrowOptions({ pathname: '/shops/[id]/orders', params: { id } }, 'Wróć do zamówień'),
      }}
    />
  );

  if (!order) {
    return (
      <Page>
        {header}
        <ThemedText type="title">Zamówienie</ThemedText>
        {error ? (
          <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
            <ThemedText themeColor="danger">{error.message}</ThemedText>
            <Button
              title="Spróbuj ponownie"
              variant="secondary"
              icon="refresh"
              onPress={refresh}
              style={styles.start}
            />
          </View>
        ) : (
          <ActivityIndicator style={styles.loader} />
        )}
      </Page>
    );
  }

  const [color, background] = ORDER_STATUS_COLORS[order.status];
  const money = (amount: string) => formatMoney(amount, order.currency);
  const shipping = order.shipping ?? order.billing;
  const separateBilling = order.billing && order.shipping && !sameAddress(order.billing, order.shipping);
  const open = (url: string) => Linking.openURL(url).catch(() => notify.error('Nie udało się otworzyć.'));

  return (
    <Page refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={refresh} />}>
      {header}
      <View style={styles.header}>
        <ThemedText type="title">Nr {order.number}</ThemedText>
        <View style={styles.headerLine}>
          <Badge label={order.status_display} color={color} background={background} />
          <ThemedText type="small" themeColor="textSecondary">
            Złożone {formatTime(order.placed_at)}
          </ThemedText>
        </View>
      </View>

      <Card title="Obsługa zamówienia">
        <OrderActions
          shopId={id}
          order={order}
          platform={shop?.platform}
          onChanged={(changed) => writeQuery(path, changed)}
        />
      </Card>

      <Card title="Produkty">
        {order.lines.map((line, index) => (
          <View key={`${line.sku}-${index}`} style={[styles.line, { borderTopColor: theme.border }]}>
            <View style={styles.flex}>
              <ThemedText type="smallBold">{line.name}</ThemedText>
              <ThemedText type="small" themeColor="textSecondary">
                {[line.sku, `${line.quantity} × ${money(line.price)}`].filter(Boolean).join(', ')}
              </ThemedText>
            </View>
            <ThemedText type="smallBold" style={styles.digits}>
              {money(line.total)}
            </ThemedText>
          </View>
        ))}
        <View style={[styles.totals, { borderTopColor: theme.border }]}>
          <Amount label="Produkty" value={money(order.products_total)} />
          <Amount label="Dostawa" value={money(order.shipping_total)} />
          {Number(order.discount_total) ? (
            <Amount label="Rabat" value={`−${money(order.discount_total)}`} />
          ) : null}
          <Amount label="Razem" value={money(order.total)} strong />
        </View>
      </Card>

      <Card title="Klient">
        <ThemedText type="smallBold">{order.customer_name || 'Bez imienia i nazwiska'}</ThemedText>
        {order.email ? (
          <ThemedText type="small" themeColor="textSecondary" selectable>
            {order.email}
          </ThemedText>
        ) : null}
        {order.phone ? (
          <ThemedText type="small" themeColor="textSecondary" selectable>
            {order.phone}
          </ThemedText>
        ) : null}
        {order.email || order.phone ? (
          <View style={styles.actions}>
            {order.email ? (
              <Button
                title="Napisz e-mail"
                icon="mail"
                variant="secondary"
                onPress={() => open(mailto(order))}
              />
            ) : null}
            {order.phone ? (
              <Button
                title="Zadzwoń"
                icon="phone"
                variant="secondary"
                onPress={() => open(`tel:${order.phone.replace(/[^\d+]/g, '')}`)}
              />
            ) : null}
          </View>
        ) : null}
      </Card>

      {order.customer_note ? (
        <Card title="Uwagi klienta">
          <ThemedText selectable>{order.customer_note}</ThemedText>
        </Card>
      ) : null}

      <Card title="Dostawa">
        {order.shipping_method ? <ThemedText type="smallBold">{order.shipping_method}</ThemedText> : null}
        {shipping ? (
          <AddressLines address={shipping} />
        ) : (
          <ThemedText type="small" themeColor="textSecondary">
            Klient nie podał adresu.
          </ThemedText>
        )}
        {order.tracking_number ? (
          <ThemedText type="small" selectable>
            Przesyłka {order.tracking_number}
            {order.carrier ? ` (${order.carrier})` : ''}
          </ThemedText>
        ) : null}
      </Card>

      <Card title="Płatność">
        <ThemedText type="smallBold">{order.payment_method || 'Bez wybranej metody'}</ThemedText>
        {separateBilling ? (
          <>
            <ThemedText type="small" themeColor="textSecondary">
              Dane do faktury
            </ThemedText>
            <AddressLines address={order.billing!} />
          </>
        ) : order.billing ? (
          <ThemedText type="small" themeColor="textSecondary">
            Dane do faktury takie jak adres dostawy.
          </ThemedText>
        ) : null}
      </Card>

      <Card title="Notatki zespołu">
        <OrderNotes
          shopId={id}
          orderId={orderId}
          notes={order.notes}
          onChange={(notes) => writeQuery(path, { ...order, notes })}
        />
      </Card>

      <ThemedText type="small" themeColor="textSecondary">
        Dane odczytaliśmy ze sklepu przy otwarciu zamówienia i nigdzie ich nie zapisujemy. Notatki zespołu trzymamy u
        nas, sklep ich nie ma.
      </ThemedText>
    </Page>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  const theme = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <ThemedText type="heading">{title}</ThemedText>
      {children}
    </View>
  );
}

function Amount({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <View style={styles.amount}>
      <ThemedText type={strong ? 'smallBold' : 'small'} themeColor={strong ? 'text' : 'textSecondary'}>
        {label}
      </ThemedText>
      <ThemedText type={strong ? 'smallBold' : 'small'} style={styles.digits}>
        {value}
      </ThemedText>
    </View>
  );
}

function AddressLines({ address }: { address: OrderAddress }) {
  const lines = [
    address.name,
    address.company,
    ...address.lines,
    [address.postcode, address.city].filter(Boolean).join(' '),
    address.country,
    address.phone ? `tel. ${address.phone}` : '',
  ].filter(Boolean);
  return (
    <View>
      {lines.map((line, index) => (
        <ThemedText key={index} type="small" selectable>
          {line}
        </ThemedText>
      ))}
    </View>
  );
}

function mailto(order: ShopOrderDetail) {
  return `mailto:${order.email}?subject=${encodeURIComponent(`Zamówienie ${order.number}`)}`;
}

function sameAddress(a: OrderAddress, b: OrderAddress) {
  return JSON.stringify(a) === JSON.stringify(b);
}

const styles = StyleSheet.create({
  loader: {
    marginVertical: Spacing.six,
  },
  header: {
    gap: Spacing.two,
  },
  headerLine: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: Spacing.two,
  },
  card: {
    gap: Spacing.two,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  flex: {
    flex: 1,
  },
  line: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: Spacing.three,
    paddingTop: Spacing.two,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  totals: {
    gap: Spacing.one,
    paddingTop: Spacing.two,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  amount: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: Spacing.three,
  },
  digits: {
    fontVariant: ['tabular-nums'],
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
    marginTop: Spacing.one,
  },
  start: {
    alignSelf: 'flex-start',
  },
});
