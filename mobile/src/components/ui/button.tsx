import { ActivityIndicator, Pressable, StyleSheet, View, type PressableProps } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

import { Icon, type IconName } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import { Fonts, Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export type ButtonProps = Omit<PressableProps, 'children'> & {
  title: string;
  variant?: 'primary' | 'accent' | 'secondary' | 'ghost' | 'danger';
  size?: 'regular' | 'large';
  icon?: IconName;
  loading?: boolean;
};

// Grows a little under the pointer and gives way when pressed.
const HOVER_SCALE = 1.03;
const PRESS_SCALE = 0.96;

export function Button({
  title,
  variant = 'primary',
  size = 'regular',
  icon,
  loading,
  disabled,
  style,
  onHoverIn,
  onHoverOut,
  onPressIn,
  onPressOut,
  ...rest
}: ButtonProps) {
  const theme = useTheme();
  const scale = useSharedValue(1);
  const hovered = useSharedValue(false);
  const scaleStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.get() }] }));
  const inactive = !!(disabled || loading);
  const animateTo = (value: number) => scale.set(withTiming(inactive ? 1 : value, { duration: 140 }));
  const look = {
    primary: { background: theme.primary, color: theme.onPrimary, border: theme.primary },
    accent: { background: theme.accent, color: theme.onAccent, border: theme.accent },
    secondary: { background: theme.surface, color: theme.text, border: theme.border },
    ghost: { background: 'transparent', color: theme.primary, border: 'transparent' },
    danger: { background: 'transparent', color: theme.danger, border: theme.danger },
  }[variant];

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: inactive, busy: !!loading }}
      disabled={inactive}
      // The Pressable only takes the caller's layout; the visible button inside is what moves.
      style={(state) => (typeof style === 'function' ? style(state) : style)}
      onHoverIn={(event) => {
        hovered.set(true);
        animateTo(HOVER_SCALE);
        onHoverIn?.(event);
      }}
      onHoverOut={(event) => {
        hovered.set(false);
        animateTo(1);
        onHoverOut?.(event);
      }}
      onPressIn={(event) => {
        animateTo(PRESS_SCALE);
        onPressIn?.(event);
      }}
      onPressOut={(event) => {
        animateTo(hovered.get() ? HOVER_SCALE : 1);
        onPressOut?.(event);
      }}
      {...rest}>
      {({ pressed }) => (
        <Animated.View
          style={[
            styles.button,
            size === 'large' && styles.large,
            { backgroundColor: look.background, borderColor: look.border },
            { opacity: disabled ? 0.45 : pressed ? 0.85 : 1 },
            scaleStyle,
          ]}>
          {loading ? (
            <ActivityIndicator color={look.color} />
          ) : (
            <View style={styles.content}>
              {icon ? <Icon name={icon} size={size === 'large' ? 20 : 17} tintColor={look.color} /> : null}
              <ThemedText style={[styles.title, size === 'large' && styles.largeTitle, { color: look.color }]}>
                {title}
              </ThemedText>
            </View>
          )}
        </Animated.View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 48,
    borderRadius: Radius.medium,
    borderWidth: 1.5,
    paddingHorizontal: Spacing.four,
    alignItems: 'center',
    justifyContent: 'center',
  },
  large: {
    minHeight: 56,
    paddingHorizontal: Spacing.five,
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  title: {
    fontFamily: Fonts.bodySemiBold,
    fontSize: 16,
  },
  largeTitle: {
    fontSize: 17,
  },
});
