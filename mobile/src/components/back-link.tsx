import { router, type Href } from 'expo-router';
import { Platform, Pressable, StyleSheet } from 'react-native';

import { Icon } from '@/components/icon';
import { Spacing } from '@/constants/theme';

/** Web only: a back arrow by the title, as the navigator draws one only with history (not after a reload). */
export function backArrowOptions(fallback: Href, label: string) {
  if (Platform.OS !== 'web') return {};
  const goBack = () => (router.canGoBack() ? router.back() : router.replace(fallback));
  return { headerLeft: () => <HeaderArrow label={label} onPress={goBack} /> };
}

/** For screens that mustn't lead back (e.g. payment result after the gateway): the arrow always goes to `target`. */
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
