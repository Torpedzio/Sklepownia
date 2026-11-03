import { ActivityIndicator, Pressable, StyleSheet, View, type PressableProps } from 'react-native';

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

export function Button({ title, variant = 'primary', size = 'regular', icon, loading, disabled, style, ...rest }: ButtonProps) {
  const theme = useTheme();
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
      accessibilityState={{ disabled: !!(disabled || loading), busy: !!loading }}
      disabled={disabled || loading}
      style={(state) => [
        styles.button,
        size === 'large' && styles.large,
        { backgroundColor: look.background, borderColor: look.border },
        { opacity: disabled ? 0.45 : state.pressed ? 0.85 : 1 },
        typeof style === 'function' ? style(state) : style,
      ]}
      {...rest}>
      {loading ? (
        <ActivityIndicator color={look.color} />
      ) : (
        <View style={styles.content}>
          {icon ? <Icon name={icon} size={size === 'large' ? 20 : 17} tintColor={look.color} /> : null}
          <ThemedText style={[styles.title, size === 'large' && styles.largeTitle, { color: look.color }]}>{title}</ThemedText>
        </View>
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
