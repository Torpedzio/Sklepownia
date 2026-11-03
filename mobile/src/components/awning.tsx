import { StyleSheet, View } from 'react-native';

import { useTheme } from '@/hooks/use-theme';

type AwningProps = { stripes?: number; height?: number; /** Second stripe color; white by default. */ altColor?: string };

/** A striped shop awning with scalloped edges: the brand's signature, always at the top edge. */
export function Awning({ stripes = 24, height = 18, altColor }: AwningProps) {
  const theme = useTheme();
  return (
    <View style={[styles.row, { height }]} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      {Array.from({ length: stripes }, (_, i) => (
        <View
          key={i}
          style={[styles.stripe, { backgroundColor: i % 2 === 0 ? theme.accent : (altColor ?? theme.receipt) }]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    width: '100%',
  },
  stripe: {
    flex: 1,
    borderBottomLeftRadius: 999,
    borderBottomRightRadius: 999,
  },
});
