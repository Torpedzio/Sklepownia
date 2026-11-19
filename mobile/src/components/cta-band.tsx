import type { PropsWithChildren } from 'react';
import { StyleSheet, View } from 'react-native';

import { Awning } from '@/components/awning';
import { ThemedText } from '@/components/themed-text';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export function CtaBand({ title, children }: PropsWithChildren<{ title: string }>) {
  const theme = useTheme();
  return (
    <View style={{ backgroundColor: theme.primary }}>
      <Awning tone="green" />
      <View style={styles.band}>
        <ThemedText type="title" style={{ color: theme.onPrimary }}>
          {title}
        </ThemedText>
        <View style={styles.actions}>{children}</View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  band: {
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
    paddingHorizontal: Spacing.four,
    paddingVertical: Spacing.six,
    gap: Spacing.four,
    alignItems: 'flex-start',
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
});
