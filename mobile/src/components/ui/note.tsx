import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

/** `warning` when a change has a side effect worth noticing. */
export function Note({ children, warning }: { children: string; warning?: boolean }) {
  const theme = useTheme();
  return (
    <View style={[styles.note, { backgroundColor: warning ? theme.accentMuted : theme.surfaceMuted }]}>
      <ThemedText type="small" themeColor={warning ? 'text' : 'textSecondary'}>
        {children}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  note: {
    padding: Spacing.three,
    borderRadius: Radius.medium,
  },
});
