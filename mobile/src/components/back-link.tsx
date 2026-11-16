import { router, type Href } from 'expo-router';
import { Platform, Pressable, StyleSheet } from 'react-native';

import { Icon } from '@/components/icon';
import { Spacing } from '@/constants/theme';

/**
 * Header options with a back arrow beside the title on the web, where the navigator only draws one
 * when there's history to go back to (not after a page reload). Phones keep their own header arrow.
 */
export function backArrowOptions(fallback: Href, label: string) {
  if (Platform.OS !== 'web') return {};
  const goBack = () => (router.canGoBack() ? router.back() : router.replace(fallback));
  return { headerLeft: () => <HeaderArrow label={label} onPress={goBack} /> };
}

/**
 * Header options for a screen that shouldn't lead back to where it came from, like the payment
 * result after the gateway: the arrow leaves for `target` on every platform, with or without history.
 */
export function exitArrowOptions(target: Href, label: string) {
  return {
    headerBackVisible: false,
    gestureEnabled: false,
    headerLeft: () => <HeaderArrow label={label} onPress={() => router.dismissTo(target)} />,
  };
}

function HeaderArrow({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      hitSlop={Spacing.two}
      style={({ hovered }) => [styles.arrow, hovered && styles.hovered]}>
      <Icon name="chevronLeft" size={24} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  arrow: {
    marginLeft: Spacing.three,
    marginRight: Spacing.one,
    padding: Spacing.one,
  },
  hovered: {
    opacity: 0.6,
  },
});
