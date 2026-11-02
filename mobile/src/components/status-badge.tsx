import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing, type ThemeColor } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { ShopStatus } from '@/lib/types';

const STATUS_COLOR: Record<ShopStatus, ThemeColor> = {
  pending: 'warning',
  provisioning: 'warning',
  active: 'success',
  failed: 'danger',
  suspended: 'textSecondary',
  deleted: 'textSecondary',
};

export function StatusBadge({ status, label }: { status: ShopStatus; label: string }) {
  const theme = useTheme();
  const color = theme[STATUS_COLOR[status]];

  return (
    <View style={[styles.badge, { borderColor: color }]}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <ThemedText type="small" style={{ color }}>
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
    paddingHorizontal: Spacing.two,
    paddingVertical: Spacing.half,
    borderRadius: Spacing.three,
    borderWidth: 1,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
});
