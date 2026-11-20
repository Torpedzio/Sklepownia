import { router, Stack, useLocalSearchParams } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { Page } from '@/components/page';
import { ProductForm } from '@/components/product-form';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useApiQuery } from '@/hooks/use-api-query';
import { writeQuery } from '@/lib/query-cache';
import type { ShopDetail, ShopProducts } from '@/lib/types';

/** A simple product, added in the shop right away. */
export default function NewProductScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { data: shop } = useApiQuery<ShopDetail>(`/shops/${id}/`);
  // The list knows the shop's currency, and is usually still loaded from the screen before.
  const { data: list } = useApiQuery<ShopProducts>(`/shops/${id}/products/`);

  return (
    <Page maxWidth={760}>
      <Stack.Screen
        options={{
          title: 'Nowy produkt',
          ...backArrowOptions({ pathname: '/shops/[id]/products', params: { id } }, 'Wróć do produktów'),
        }}
      />
      <View style={styles.header}>
        <ThemedText type="title">Nowy produkt</ThemedText>
        <ThemedText themeColor="textSecondary">
          Dodamy go od razu w sklepie{shop ? ` „${shop.name}”` : ''}. Zdjęcia i warianty dodasz na razie w panelu
          sklepu.
        </ThemedText>
      </View>
      <ProductForm
        shopId={id}
        platform={shop?.platform}
        currency={list?.currency ?? 'PLN'}
        onSaved={(saved) => {
          writeQuery(`/shops/${id}/products/${saved.external_id}/`, saved);
          router.replace({ pathname: '/shops/[id]/products/[productId]', params: { id, productId: saved.external_id } });
        }}
      />
    </Page>
  );
}

const styles = StyleSheet.create({
  header: {
    gap: Spacing.one,
  },
});
