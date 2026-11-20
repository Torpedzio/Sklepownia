import { router, Stack, useLocalSearchParams } from 'expo-router';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { Page } from '@/components/page';
import { ProductForm } from '@/components/product-form';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Spacing } from '@/constants/theme';
import { useApiQuery } from '@/hooks/use-api-query';
import { writeQuery } from '@/lib/query-cache';
import type { ProductDetail, ShopDetail } from '@/lib/types';

/** The product's name, prices, description, categories and visibility, saved in the shop. */
export default function EditProductScreen() {
  const { id, productId } = useLocalSearchParams<{ id: string; productId: string }>();
  const path = `/shops/${id}/products/${productId}/`;
  const { data: shop } = useApiQuery<ShopDetail>(`/shops/${id}/`);
  const { data: product, error, refresh } = useApiQuery<ProductDetail>(path);
  const back = { pathname: '/shops/[id]/products/[productId]', params: { id, productId } } as const;

  return (
    <Page maxWidth={760}>
      <Stack.Screen options={{ title: 'Edytuj produkt', ...backArrowOptions(back, 'Wróć do produktu') }} />
      <View style={styles.header}>
        <ThemedText type="title">Edytuj produkt</ThemedText>
        {product ? <ThemedText themeColor="textSecondary">{product.name}</ThemedText> : null}
      </View>
      {product ? (
        <ProductForm
          shopId={id}
          platform={shop?.platform}
          currency={product.currency}
          product={product}
          onSaved={(saved) => {
            writeQuery(path, saved);
            if (router.canGoBack()) router.back();
            else router.replace(back);
          }}
        />
      ) : error ? (
        <View style={styles.error}>
          <ThemedText themeColor="danger">{error.message}</ThemedText>
          <Button title="Spróbuj ponownie" variant="secondary" icon="refresh" onPress={refresh} />
        </View>
      ) : (
        <ActivityIndicator style={styles.loader} />
      )}
    </Page>
  );
}

const styles = StyleSheet.create({
  header: {
    gap: Spacing.one,
  },
  error: {
    gap: Spacing.two,
    alignItems: 'flex-start',
  },
  loader: {
    marginVertical: Spacing.six,
  },
});
