import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Brand } from '@/constants/brand';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

/** A tiny awning over a doorway, next to the wordmark. */
/** `compact` drops the wordmark where space is tight. */
export function Logo({ inverted = false, compact = false }: { inverted?: boolean; compact?: boolean }) {
  const theme = useTheme();
  return (
    <View style={styles.row} accessibilityRole="header" accessibilityLabel={Brand.name}>
      <View style={styles.mark}>
        <View style={styles.awning}>
          {[0, 1, 2, 3].map((i) => (
            <View key={i} style={[styles.stripe, { backgroundColor: i % 2 === 0 ? theme.accent : theme.receipt }]} />
          ))}
        </View>
        <View style={[styles.door, { backgroundColor: theme.primary }]} />
      </View>
      {compact ? null : (
        <ThemedText type="heading" style={[styles.word, inverted && { color: theme.receipt }]}>
          {Brand.name}
        </ThemedText>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  mark: {
    width: 28,
    alignItems: 'center',
  },
  awning: {
    flexDirection: 'row',
    width: 28,
    height: 10,
  },
  stripe: {
    flex: 1,
    borderBottomLeftRadius: 4,
    borderBottomRightRadius: 4,
  },
  door: {
    width: 20,
    height: 14,
    marginTop: 2,
    borderTopLeftRadius: 3,
    borderTopRightRadius: 3,
  },
  word: {
    fontSize: 20,
    letterSpacing: -0.4,
  },
});
