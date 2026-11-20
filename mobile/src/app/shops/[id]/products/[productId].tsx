import { Link, router, Stack, useLocalSearchParams } from 'expo-router';
import { useState, type ReactNode } from 'react';
import { ActivityIndicator, Linking, RefreshControl, StyleSheet, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { Page } from '@/components/page';
import { ProductImage, stockLabel } from '@/components/product-row';
import { Badge } from '@/components/status-badge';
import { StockEditor } from '@/components/stock-editor';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import { formatMoney } from '@/lib/format';
import { readQuery, writeQuery } from '@/lib/query-cache';
import type { ProductDetail, ShopDetail, ShopProducts } from '@/lib/types';

/** One product as the shop has it now: its stock, editing, hiding and (for the owner) deleting it. */
export default function ShopProductScreen() {
  const { id, productId } = useLocalSearchParams<{ id: string; productId: string }>();
  const theme = useTheme();
  const notify = useNotify();
  const path = `/shops/${id}/products/${productId}/`;
  const { data: shop } = useApiQuery<ShopDetail>(`/shops/${id}/`);
  const { data: product, error, isRefreshing, refresh } = useApiQuery<ProductDetail>(path);
  const [busy, setBusy] = useState<'visibility' | 'delete' | null>(null);

  const header = (
    <Stack.Screen
      options={{
        title: product?.name ?? 'Produkt',
        ...backArrowOptions({ pathname: '/shops/[id]/products', params: { id } }, 'Wróć do produktów'),
      }}
    />
  );

  if (!product) {
    return (
      <Page>
        {header}
        <ThemedText type="title">Produkt</ThemedText>
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

  const money = (amount: string) => formatMoney(amount, product.currency);
  const panel = shop?.panel_name ?? 'panel sklepu';
  const listPath = `/shops/${id}/products/`;

  async function toggleVisibility() {
    if (!product) return;
    setBusy('visibility');
    try {
      const saved = await api<ProductDetail>(path, { method: 'PATCH', body: { visible: !product.visible } });
      writeQuery(path, saved);
      notify.success(saved.visible ? 'Produkt jest widoczny w sklepie.' : 'Produkt jest ukryty przed klientami.');
    } catch (e) {
      notify.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    if (!product) return;
    const sure = await confirm(
      'Usunąć produkt?',
      shop?.platform === 'woocommerce'
        ? `„${product.name}” zniknie ze sklepu i trafi do kosza w ${panel.replace(/^panel\b/, 'panelu')}, skąd przez 30 dni można go przywrócić.`
        : `„${product.name}” zniknie ze sklepu na stałe. Złożone już zamówienia z nim zostaną.`,
      'Usuń produkt',
    );
    if (!sure) return;
    setBusy('delete');
    try {
      await api(path, { method: 'DELETE' });
      notify.success(`Usunięte: „${product.name}”.`);
      // The list on the screen before shows it until it's read again.
      const list = readQuery(listPath).data as ShopProducts | undefined;
      if (list) {
        writeQuery(listPath, {
          ...list,
          products: list.products.filter((item) => item.external_id !== product.external_id),
        });
      }
      if (router.canGoBack()) router.back();
      else router.replace({ pathname: '/shops/[id]/products', params: { id } });
    } catch (e) {
      notify.error((e as Error).message);
      setBusy(null);
    }
  }

  return (
    <Page refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={refresh} />}>
      {header}
      <View style={styles.header}>
        <ProductImage uri={product.image} size={96} />
        <View style={styles.headerText}>
          <ThemedText type="subtitle">{product.name}</ThemedText>
          <View style={styles.badges}>
            <Badge
              label={stockLabel(product)}
              color={product.in_stock ? 'success' : 'danger'}
              background={product.in_stock ? 'primaryMuted' : 'dangerMuted'}
            />
            {product.visible ? null : <Badge label="Ukryty" color="textSecondary" background="surfaceMuted" />}
          </View>
        </View>
      </View>

      <View style={styles.actions}>
        <Link href={{ pathname: '/shops/[id]/products/[productId]/edit', params: { id, productId } }} asChild>
          <Button title="Edytuj" icon="edit" />
        </Link>
        <Button
          title={product.visible ? 'Ukryj przed klientami' : 'Pokaż w sklepie'}
          icon={product.visible ? 'hide' : 'show'}
          variant="secondary"
          loading={busy === 'visibility'}
          disabled={busy !== null}
          onPress={toggleVisibility}
        />
      </View>

      <Card title="Stan magazynowy">
        <StockEditor
          key={product.stock ?? 'none'}
          shopId={id}
          product={product}
          onChanged={(changed) => writeQuery(path, changed)}
        />
      </Card>

      <Card title="Cena i dane">
        <Line
          label={product.has_variants ? 'Cena od' : 'Cena'}
          value={product.price === null ? 'Bez ceny' : money(product.price)}
        />
        {product.regular_price ? <Line label="Przed promocją" value={money(product.regular_price)} /> : null}
        <Line label="SKU" value={product.sku || 'Brak'} />
        <Line
          label="Kategorie"
          value={product.categories.map((category) => category.name).join(', ') || 'Bez kategorii'}
        />
        <Line
          label="W sklepie"
          value={product.visible ? 'Widoczny dla klientów' : 'Ukryty: klienci go nie widzą'}
        />
        {product.url ? (
          <Button
            title="Zobacz w sklepie"
            icon="external"
            variant="secondary"
            onPress={() => Linking.openURL(product.url).catch(() => notify.error('Nie udało się otworzyć.'))}
            style={styles.start}
          />
        ) : null}
      </Card>

      {product.description ? (
        <Card title="Opis">
          <ThemedText type="small" selectable>
            {product.description}
          </ThemedText>
        </Card>
      ) : null}

      {shop?.role === 'owner' ? (
        <Card title="Usuwanie">
          <ThemedText type="small" themeColor="textSecondary">
            {shop.platform === 'woocommerce'
              ? 'Usunięty produkt trafi do kosza w panelu sklepu, skąd przez 30 dni można go przywrócić.'
              : 'Usunięcia nie da się cofnąć. Żeby tylko wstrzymać sprzedaż, ukryj produkt przed klientami.'}
          </ThemedText>
          <Button
            title="Usuń produkt"
            icon="trash"
            variant="danger"
            loading={busy === 'delete'}
            disabled={busy !== null}
            onPress={remove}
            style={styles.start}
          />
        </Card>
      ) : null}

      <ThemedText type="small" themeColor="textSecondary">
        Produkt odczytaliśmy ze sklepu przy otwarciu.{' '}
        {shop?.role === 'staff'
          ? 'Zdjęcia i warianty zmienia na razie właściciel sklepu w jego panelu.'
          : `Zdjęcia i warianty zmienisz na razie w ${panel.replace(/^panel\b/, 'panelu')}.`}
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

function Line({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.line}>
      <ThemedText type="small" themeColor="textSecondary">
        {label}
      </ThemedText>
      <ThemedText type="small" style={styles.value} selectable>
        {value}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  loader: {
    marginVertical: Spacing.six,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
  },
  headerText: {
    flex: 1,
    gap: Spacing.two,
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
  },
  badges: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
  },
  card: {
    gap: Spacing.two,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  line: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: Spacing.three,
  },
  value: {
    flexShrink: 1,
    textAlign: 'right',
  },
  start: {
    alignSelf: 'flex-start',
  },
});
