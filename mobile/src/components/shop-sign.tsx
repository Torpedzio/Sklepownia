import { Link } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { Awning } from '@/components/awning';
import { Icon } from '@/components/icon';
import { StatusBadge } from '@/components/status-badge';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Shop } from '@/lib/types';

/** A shop on the dashboard, drawn as a small shopfront with its own awning. */
export function ShopSign({ shop }: { shop: Shop }) {
  const theme = useTheme();

  return (
    <Link href={{ pathname: '/shops/[id]', params: { id: shop.id } }} asChild>
      <Pressable
        accessibilityRole="link"
        accessibilityLabel={`${shop.name}, ${shop.status_display}${shop.is_test ? ', sklep testowy' : ''}`}
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
              <StatusBadge status={shop.status} label={shop.status_display} />
              {shop.is_test ? <TestBadge /> : null}
            </View>
          </View>
          <Icon name="chevron" size={18} color="textSecondary" />
        </View>
      </Pressable>
    </Link>
  );
}

/** Marks shops from before paid plans: they work without a plan and don't count towards it. */
export function TestBadge() {
  const theme = useTheme();
  return (
    <View style={[styles.test, { borderColor: theme.border }]} accessibilityLabel="Sklep testowy">
      <ThemedText type="smallBold" themeColor="textSecondary">
        Testowy
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
  test: {
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
