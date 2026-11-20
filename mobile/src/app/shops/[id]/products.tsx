import { Link, Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, RefreshControl, StyleSheet, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { Page } from '@/components/page';
import { ProductRow } from '@/components/product-row';
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
import type { ShopDetail, ShopProducts } from '@/lib/types';

const STOCK_FILTERS = [
  { value: '', label: 'Wszystkie' },
  { value: 'out_of_stock', label: 'Brak w magazynie' },
];
const SEARCH_DELAY_MS = 400;

/** The shop's products, read from the shop: searched by name and filtered by what's sold out. */
export default function ShopProductsScreen() {
  const params = useLocalSearchParams<{ id: string; stock?: string }>();
  const id = params.id;
  const theme = useTheme();
  const notify = useNotify();
  const [stock, setStock] = useState(params.stock === 'out_of_stock' ? 'out_of_stock' : '');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search]);

  const filters: [string, string][] = [];
  if (query) filters.push(['q', query]);
  if (stock) filters.push(['stock', stock]);
  const path = `/shops/${id}/products/${queryString(filters)}`;

  const { data: shop } = useApiQuery<ShopDetail>(`/shops/${id}/`);
  const { data: first, error, isRefreshing, refresh } = useApiQuery<ShopProducts>(path);
  // Pages loaded with "Pokaż więcej", for the filters they were loaded with.
  const [more, setMore] = useState<{ path: string; pages: ShopProducts[] }>({ path, pages: [] });
  const [loadingMore, setLoadingMore] = useState(false);
  const morePages = more.path === path ? more.pages : [];

  const header = (
    <>
      <Stack.Screen
        options={{
          title: 'Produkty',
          ...backArrowOptions({ pathname: '/shops/[id]', params: { id } }, 'Wróć do sklepu'),
        }}
      />
      <View style={styles.header}>
        <View style={styles.headerText}>
          <ThemedText type="title">Produkty</ThemedText>
          {shop ? <ThemedText themeColor="textSecondary">{shop.name}</ThemedText> : null}
        </View>
        <Link href={{ pathname: '/shops/[id]/products/new', params: { id } }} asChild>
          <Button title="Dodaj produkt" icon="plus" />
        </Link>
      </View>
    </>
  );

  const filtersView = (
    <View style={styles.filters}>
      <TextField
        label="Szukaj"
        placeholder={shop?.platform === 'magento' ? 'Nazwa albo SKU' : 'Nazwa produktu'}
        value={search}
        onChangeText={setSearch}
        autoCapitalize="none"
        autoCorrect={false}
        returnKeyType="search"
        onSubmitEditing={() => setQuery(search.trim())}
      />
      <ChipSelect label="Pokaż" options={STOCK_FILTERS} value={stock} onChange={setStock} />
    </View>
  );

  if (!first) {
    return (
      <Page>
        {header}
        {filtersView}
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

  const pages = [first, ...morePages];
  const products = pages.flatMap((page) => page.products);
  const hasMore = pages[pages.length - 1].has_more;

  async function reload() {
    setMore({ path, pages: [] });
    await refresh();
  }

  async function loadMore() {
    setLoadingMore(true);
    try {
      const page = await api<ShopProducts>(
        `/shops/${id}/products/${queryString([...filters, ['page', String(pages.length + 1)]])}`,
      );
      setMore({ path, pages: [...morePages, page] });
    } catch (e) {
      notify.error((e as Error).message);
    } finally {
      setLoadingMore(false);
    }
  }

  let empty: { title: string; text: string } | null = null;
  if (!products.length) {
    if (query) {
      empty = { title: 'Nic nie znaleźliśmy', text: `Żaden produkt nie pasuje do „${query}”.` };
    } else if (stock) {
      empty = { title: 'Niczego nie brakuje', text: 'Wszystkie produkty, których sztuki sklep liczy, są w magazynie.' };
    } else {
      empty = {
        title: 'Sklep nie ma jeszcze produktów',
        text: 'Dodaj pierwszy produkt: wystarczy nazwa i cena. Opis, kategorie i stan magazynowy są nieobowiązkowe.',
      };
    }
  }

  return (
    <Page refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={reload} />}>
      {header}
      {filtersView}

      {empty ? (
        <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          <ThemedText type="heading">{empty.title}</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            {empty.text}
          </ThemedText>
          {query || stock ? (
            <Button
              title={query ? 'Wyczyść wyszukiwanie' : 'Pokaż wszystkie'}
              variant="secondary"
              style={styles.start}
              onPress={() => {
                if (query) {
                  setSearch('');
                  setQuery('');
                } else {
                  setStock('');
                }
              }}
            />
          ) : null}
        </View>
      ) : (
        <View style={[styles.list, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          {products.map((product, index) => (
            <ProductRow
              key={product.external_id}
              shopId={id}
              product={product}
              currency={first.currency}
              first={index === 0}
            />
          ))}
        </View>
      )}

      {hasMore ? (
        <Button
          title="Pokaż więcej"
          variant="secondary"
          onPress={loadMore}
          loading={loadingMore}
          style={styles.start}
        />
      ) : null}

      <ThemedText type="small" themeColor="textSecondary">
        Produkty czytamy ze sklepu przy każdym otwarciu listy, od najnowszych, także ukryte przed klientami.
      </ThemedText>
    </Page>
  );
}

const styles = StyleSheet.create({
  loader: {
    marginVertical: Spacing.six,
  },
  header: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: Spacing.three,
  },
  headerText: {
    gap: Spacing.one,
    flexShrink: 1,
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
