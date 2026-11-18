import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { useTheme } from '@/hooks/use-theme';
import { useWindowDimensions } from '@/hooks/use-window-dimensions';

/** Every awning has the same stripes: this tall, about this wide, green first. */
export const AWNING_HEIGHT = 16;
const STRIPE_WIDTH = 40;

type AwningProps = {
  /**
   * What the awning hangs over, so both stripes stay visible:
   * `page` the page background, `card` a white card, `green` a green band.
   */
  tone?: 'page' | 'card' | 'green';
};

/** A striped shop awning with scalloped edges: the brand's signature, always at the top edge. */
export function Awning({ tone = 'page' }: AwningProps) {
  const theme = useTheme();
  const [width, setWidth] = useState(0);
  // Across the page it is as wide as the window, so it has stripes before it is measured, in the page from the
  // server too.
  const estimate = useWindowDimensions().width;
  const across = width || (tone === 'page' ? estimate : 0);
  // Count from the width, so stripes are the same size on a card and across a wide screen.
  const stripes = across ? Math.max(1, Math.round(across / STRIPE_WIDTH)) : 0;
  const [first, second] = {
    page: [theme.primary, theme.receipt],
    card: [theme.primary, theme.primaryMuted],
    green: [theme.primaryMuted, theme.receipt],
  }[tone];

  return (
    <View
      style={styles.row}
      onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants">
      {Array.from({ length: stripes }, (_, i) => (
        <View key={i} style={[styles.stripe, { backgroundColor: i % 2 === 0 ? first : second }]} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    width: '100%',
    height: AWNING_HEIGHT,
  },
  stripe: {
    flex: 1,
    // Clamped to the stripe height, so each stripe ends in a rounded scallop.
    borderBottomLeftRadius: AWNING_HEIGHT,
    borderBottomRightRadius: AWNING_HEIGHT,
  },
});
