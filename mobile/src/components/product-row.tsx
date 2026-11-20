import { Image } from 'expo-image';
import { router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { Icon } from '@/components/icon';
import { Badge } from '@/components/status-badge';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing, type ThemeColor } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { formatMoney } from '@/lib/format';
import type { Product } from '@/lib/types';

/** A product in a list; opens its details, read from the shop. */
export function ProductRow({
  shopId,
  product,
  currency,
  first,
}: {
  shopId: number | string;
  product: Product;
  currency: string;
  first: boolean;
}) {
  const theme = useTheme();
  const price = product.price === null ? 'Bez ceny' : formatMoney(product.price, currency);
  const stock = stockLabel(product);
  const [color, background]: [ThemeColor, ThemeColor] = product.in_stock
    ? ['textSecondary', 'surfaceMuted']
    : ['danger', 'dangerMuted'];

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={[product.name, price, stock, product.visible ? '' : 'ukryty'].filter(Boolean).join(', ')}
      onPress={() =>
        router.push({
          pathname: '/shops/[id]/products/[productId]',
          params: { id: String(shopId), productId: product.external_id },
        })
      }
      style={({ pressed }) => [
        styles.row,
        !first && { borderTopColor: theme.border, borderTopWidth: StyleSheet.hairlineWidth },
        pressed && styles.pressed,
      ]}>
      <ProductImage uri={product.image} size={48} />
      <View style={styles.flex}>
        <ThemedText type="smallBold" numberOfLines={2}>
          {product.name}
        </ThemedText>
        <ThemedText type="small" themeColor="textSecondary" numberOfLines={1}>
          {[product.sku, product.visible ? '' : 'ukryty w sklepie'].filter(Boolean).join(', ') || ' '}
        </ThemedText>
      </View>
      <View style={styles.end}>
        <ThemedText type="smallBold" style={styles.digits}>
          {price}
        </ThemedText>
        <Badge label={stock} color={color} background={background} />
      </View>
      <Icon name="chevron" size={16} color="textSecondary" />
    </Pressable>
  );
}

/** The product's picture, or a placeholder when it has none. */
export function ProductImage({ uri, size }: { uri: string; size: number }) {
  const theme = useTheme();
  const box = { width: size, height: size, borderRadius: Radius.small, backgroundColor: theme.surfaceMuted };
  if (!uri) {
    return (
      <View style={[box, styles.placeholder]}>
        <Icon name="cart" size={size / 2.5} color="textSecondary" />
      </View>
    );
  }
  return <Image source={{ uri }} style={box} contentFit="cover" accessibilityIgnoresInvertColors />;
}

export function stockLabel(product: Product) {
  if (product.stock !== null) return product.stock > 0 ? `${product.stock} szt.` : 'Brak';
  return product.in_stock ? 'Dostępny' : 'Brak';
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
  placeholder: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});
