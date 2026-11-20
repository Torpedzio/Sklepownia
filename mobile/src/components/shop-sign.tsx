import { Link } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { Awning } from '@/components/awning';
import { Icon } from '@/components/icon';
import { ShopStatusBadge } from '@/components/status-badge';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Shop } from '@/lib/types';

export function ShopSign({ shop }: { shop: Shop }) {
  const theme = useTheme();

  return (
    <Link href={{ pathname: '/shops/[id]', params: { id: shop.id } }} asChild>
      <Pressable
        accessibilityRole="link"
        accessibilityLabel={[shop.name, shop.status_display, shop.is_test && 'sklep testowy', shop.role === 'staff' && 'obsługujesz go w zespole']
          .filter(Boolean)
          .join(', ')}
        style={StyleSheet.flatten([
          styles.sign,
          { backgroundColor: theme.surface, borderColor: theme.border },
          // Suspended shops (beyond the plan's limit) stay on the list, greyed out.
          shop.status === 'suspended' && styles.suspended,
        ])}>
        <Awning tone="card" />
        <View style={styles.body}>
          <View style={styles.text}>
            <ThemedText type="subtitle" numberOfLines={1}>
              {shop.name}
            </ThemedText>
            <ThemedText type="small" themeColor="textSecondary" numberOfLines={1}>
              {shop.url.replace(/^https?:\/\//, '')}
            </ThemedText>
            <View style={styles.badges}>
              <ShopStatusBadge shop={shop} />
              {shop.is_test ? <TestBadge /> : null}
              {shop.role === 'staff' ? <StaffBadge /> : null}
            </View>
          </View>
          <Icon name="chevron" size={18} color="textSecondary" />
        </View>
      </Pressable>
    </Link>
  );
}

export function TestBadge() {
  return <OutlineBadge label="Testowy" accessibilityLabel="Sklep testowy" />;
}

/** Someone else's shop, run together with its owner. */
export function StaffBadge() {
  return <OutlineBadge label="Obsługujesz" accessibilityLabel="Obsługujesz ten sklep w zespole" />;
}

function OutlineBadge({ label, accessibilityLabel }: { label: string; accessibilityLabel: string }) {
  const theme = useTheme();
  return (
    <View style={[styles.outline, { borderColor: theme.border }]} accessibilityLabel={accessibilityLabel}>
      <ThemedText type="smallBold" themeColor="textSecondary">
        {label}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  suspended: {
    opacity: 0.55,
  },
  badges: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
  },
  outline: {
    alignSelf: 'flex-start',
    paddingHorizontal: Spacing.two + Spacing.one,
    paddingVertical: Spacing.half - 1,
    borderRadius: Radius.pill,
    borderWidth: 1,
  },
  sign: {
    flexBasis: 320,
    flexGrow: 1,
    borderRadius: Radius.medium,
    borderWidth: 1,
    overflow: 'hidden',
  },
  body: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
    padding: Spacing.four,
    paddingTop: Spacing.three,
  },
  text: {
    flex: 1,
    gap: Spacing.two,
  },
});
