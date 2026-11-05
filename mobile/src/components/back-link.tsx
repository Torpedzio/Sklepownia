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
  return { headerLeft: () => <BackArrow fallback={fallback} label={label} /> };
}

function BackArrow({ fallback, label }: { fallback: Href; label: string }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={() => (router.canGoBack() ? router.back() : router.replace(fallback))}
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
