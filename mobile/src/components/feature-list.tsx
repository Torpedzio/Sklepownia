import { StyleSheet, View } from 'react-native';

import { Icon } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import type { Feature } from '@/constants/content';
import { useTheme } from '@/hooks/use-theme';

/** Features in a two-column list separated by rules, not a grid of cards. */
export function FeatureList({ features }: { features: Feature[] }) {
  const theme = useTheme();
  return (
    <View style={styles.list}>
      {features.map((feature) => (
        <View key={feature.title} style={[styles.item, { borderTopColor: theme.border }]}>
          <View style={[styles.icon, { backgroundColor: theme.primaryMuted }]}>
            <Icon name={feature.icon} size={20} color="primary" />
          </View>
          <View style={styles.text}>
            <ThemedText type="heading">{feature.title}</ThemedText>
            <ThemedText themeColor="textSecondary">{feature.text}</ThemedText>
          </View>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  list: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    columnGap: Spacing.five,
  },
  item: {
    flexBasis: 300,
    flexGrow: 1,
    flexDirection: 'row',
    gap: Spacing.three,
    paddingVertical: Spacing.four,
    borderTopWidth: 1,
  },
  icon: {
    width: 40,
    height: 40,
    borderRadius: Radius.small,
    alignItems: 'center',
    justifyContent: 'center',
  },
  text: {
    flex: 1,
    gap: Spacing.one,
  },
});
