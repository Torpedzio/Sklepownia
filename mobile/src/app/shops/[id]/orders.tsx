import { Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, RefreshControl, StyleSheet, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { OrderRow } from '@/components/order-row';
import { Page } from '@/components/page';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { ChipSelect } from '@/components/ui/chip-select';
import { TextField } from '@/components/ui/text-field';
import { Radius, Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api } from '@/lib/api';
import { queryString } from '@/lib/format';
import { SALES_POLL_MS } from '@/lib/sales';
import { formatTime } from '@/lib/settings-form';
import type { OrderStatus, ShopDetail, ShopOrders } from '@/lib/types';

// In the order a shop works through them.
const STATUSES: [OrderStatus, string][] = [
  ['new', 'Nowe'],
  ['processing', 'W realizacji'],
  ['completed', 'Zrealizowane'],
  ['unfinished', 'Nieopłacone'],
  ['cancelled', 'Anulowane'],
];
const SEARCH_DELAY_MS = 400;

/** The shop's orders from the last 90 days, by status and searched by number or customer. */
export default function ShopOrdersScreen() {
  const params = useLocalSearchParams<{ id: string; status?: string }>();
  const id = params.id;
  const theme = useTheme();
  const notify = useNotify();
  const [status, setStatus] = useState<string>(
    STATUSES.some(([value]) => value === params.status) ? params.status! : '',
  );
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search]);

  const filters: [string, string][] = [];
  if (status) filters.push(['status', status]);
  if (query) filters.push(['q', query]);
  const path = `/shops/${id}/orders/${queryString(filters)}`;

  const { data: shop } = useApiQuery<ShopDetail>(`/shops/${id}/`);
  const { data: first, error, isRefreshing, refresh } = useApiQuery<ShopOrders>(path, {
    refetchInterval: (data) => (data?.refreshing ? SALES_POLL_MS : false),
  });
  // Pages loaded with "Pokaż starsze", for the filters they were loaded with.
  const [older, setOlder] = useState<{ path: string; pages: ShopOrders[] }>({ path, pages: [] });
  const [loadingMore, setLoadingMore] = useState(false);
  const olderPages = older.path === path ? older.pages : [];

  const header = (
    <>
      <Stack.Screen
        options={{
          title: 'Zamówienia',
          ...backArrowOptions({ pathname: '/shops/[id]', params: { id } }, 'Wróć do sklepu'),
        }}
      />
      <View style={styles.header}>
        <ThemedText type="title">Zamówienia</ThemedText>
        {shop ? (
          <ThemedText themeColor="textSecondary">{shop.name}, zamówienia z ostatnich 90 dni</ThemedText>
        ) : null}
      </View>
    </>
  );

  const total = first ? Object.values(first.counts).reduce((sum, count) => sum + count, 0) : 0;
  const options = [
    { value: '', label: first ? `Wszystkie (${total})` : 'Wszystkie' },
    ...STATUSES.map(([value, label]) => ({
      value,
      label: first ? `${label} (${first.counts[value]})` : label,
    })),
  ];

  const filtersView = (
    <View style={styles.filters}>
      <TextField
        label="Szukaj"
        placeholder="Numer zamówienia albo imię klienta"
        value={search}
        onChangeText={setSearch}
        autoCapitalize="none"
        autoCorrect={false}
        returnKeyType="search"
        onSubmitEditing={() => setQuery(search.trim())}
      />
      <ChipSelect label="Status" options={options} value={status} onChange={setStatus} />
    </View>
  );

  if (!first) {
    return (
      <Page>
        {header}
        {filtersView}
        {error ? (
          <ThemedText themeColor="danger">{error.message}</ThemedText>
        ) : (
          <ActivityIndicator style={styles.loader} />
        )}
      </Page>
    );
  }

  const pages = [first, ...olderPages];
  const orders = pages.flatMap((page) => page.orders);
  const hasMore = pages[pages.length - 1].has_more;

  async function reload() {
    setOlder({ path, pages: [] });
    await refresh();
  }

  async function loadMore() {
    setLoadingMore(true);
    const before: [string, string] = ['before', orders[orders.length - 1].external_id];
    try {
      const page = await api<ShopOrders>(`/shops/${id}/orders/${queryString([...filters, before])}`);
      setOlder({ path, pages: [...olderPages, page] });
    } catch (e) {
      notify.error((e as Error).message);
    } finally {
      setLoadingMore(false);
    }
  }

  let empty: { title: string; text: string } | null = null;
  if (!orders.length) {
    if (first.synced_at === null) {
      empty = first.refreshing
        ? { title: 'Za chwilę zobaczysz zamówienia', text: 'Pierwszy odczyt zamówień trwa zwykle kilka sekund.' }
        : { title: 'Zamówień jeszcze nie odczytaliśmy', text: first.error || 'Spróbujemy za kilka minut.' };
    } else if (query) {
      empty = { title: 'Nic nie znaleźliśmy', text: `Żadne zamówienie nie ma numeru ani klienta „${query}”.` };
    } else if (status) {
      empty = { title: 'Brak zamówień w tym statusie', text: 'Wybierz inny status albo pokaż wszystkie.' };
    } else {
      empty = {
        title: 'Nie ma jeszcze zamówień',
        text: 'Pokażemy je tutaj kilka minut po tym, jak klienci je złożą.',
      };
    }
  }

  return (
    <Page refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={reload} />}>
      {header}
      {filtersView}

      <ThemedText type="small" themeColor="textSecondary">
        {first.refreshing
          ? 'Odczytujemy zamówienia ze sklepu…'
          : first.synced_at
            ? `Zamówienia odczytane ze sklepu ${formatTime(first.synced_at)}.`
            : ''}
        {!first.available ? ' Sklep teraz nie działa: szczegóły zamówień otworzysz, gdy znów zadziała.' : ''}
      </ThemedText>

      {empty ? (
        <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          <ThemedText type="heading">{empty.title}</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            {empty.text}
          </ThemedText>
          {query || status ? (
            <Button
              title={query ? 'Wyczyść wyszukiwanie' : 'Pokaż wszystkie'}
              variant="secondary"
              style={styles.start}
              onPress={() => {
                if (query) {
                  setSearch('');
                  setQuery('');
                } else {
                  setStatus('');
                }
              }}
            />
          ) : null}
        </View>
      ) : (
        <View style={[styles.list, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          {orders.map((order, index) => (
            <OrderRow key={order.external_id} shopId={id} order={order} first={index === 0} />
          ))}
        </View>
      )}

      {hasMore ? (
        <Button
          title="Pokaż starsze"
          variant="secondary"
          onPress={loadMore}
          loading={loadingMore}
          style={styles.start}
        />
      ) : null}

      <ThemedText type="small" themeColor="textSecondary">
        Lista obejmuje zamówienia z ostatnich 90 dni. Pełne dane klienta i adresy czytamy ze sklepu dopiero po
        otwarciu zamówienia i nigdzie ich nie zapisujemy.
      </ThemedText>
    </Page>
  );
}

const styles = StyleSheet.create({
  loader: {
    marginVertical: Spacing.six,
  },
  header: {
    gap: Spacing.one,
  },
  filters: {
    gap: Spacing.three,
  },
  card: {
    gap: Spacing.two,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  list: {
    borderRadius: Radius.large,
    borderWidth: 1,
    paddingHorizontal: Spacing.three,
  },
  start: {
    alignSelf: 'flex-start',
  },
});
