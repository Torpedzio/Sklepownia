import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing, type ThemeColor } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { ShopStatus } from '@/lib/types';

const STATUS_COLOR: Record<ShopStatus, [ThemeColor, ThemeColor]> = {
  pending: ['warning', 'accentMuted'],
  provisioning: ['warning', 'accentMuted'],
  active: ['success', 'primaryMuted'],
  failed: ['danger', 'dangerMuted'],
  suspended: ['textSecondary', 'surfaceMuted'],
  deleted: ['textSecondary', 'surfaceMuted'],
};

export function StatusBadge({ status, label }: { status: ShopStatus; label: string }) {
  const theme = useTheme();
  const [color, background] = STATUS_COLOR[status];

  return (
    <View style={[styles.badge, { backgroundColor: theme[background] }]}>
      <View style={[styles.dot, { backgroundColor: theme[color] }]} />
      <ThemedText type="smallBold" themeColor={color}>
        {label}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.one + Spacing.half,
    alignSelf: 'flex-start',
    paddingHorizontal: Spacing.two + Spacing.one,
    paddingVertical: Spacing.half,
    borderRadius: Radius.pill,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 4,
  },
});
