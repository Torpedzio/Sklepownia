import { StyleSheet, Text, type TextProps } from 'react-native';

import { Fonts, ThemeColor } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export type ThemedTextProps = TextProps & {
  type?: 'display' | 'title' | 'subtitle' | 'heading' | 'lead' | 'default' | 'small' | 'smallBold' | 'link' | 'mono';
  themeColor?: ThemeColor;
};

export function ThemedText({ style, type = 'default', themeColor, ...rest }: ThemedTextProps) {
  const theme = useTheme();
  const color = theme[themeColor ?? (type === 'link' ? 'primary' : 'text')];

  return <Text style={[{ color }, styles[type], style]} {...rest} />;
}

// Custom fonts carry their weight in the family name, so no fontWeight here.
const styles = StyleSheet.create({
  display: {
    fontFamily: Fonts.display,
    fontSize: 52,
    lineHeight: 56,
    letterSpacing: -1.5,
  },
  title: {
    fontFamily: Fonts.display,
    fontSize: 34,
    lineHeight: 40,
    letterSpacing: -0.8,
  },
  subtitle: {
    fontFamily: Fonts.display,
    fontSize: 24,
    lineHeight: 30,
    letterSpacing: -0.4,
  },
  heading: {
    fontFamily: Fonts.displayMedium,
    fontSize: 18,
    lineHeight: 24,
  },
  lead: {
    fontFamily: Fonts.body,
    fontSize: 19,
    lineHeight: 29,
  },
  default: {
    fontFamily: Fonts.body,
    fontSize: 16,
    lineHeight: 24,
  },
  small: {
    fontFamily: Fonts.body,
    fontSize: 14,
    lineHeight: 20,
  },
  smallBold: {
    fontFamily: Fonts.bodySemiBold,
    fontSize: 14,
    lineHeight: 20,
  },
  link: {
    fontFamily: Fonts.bodySemiBold,
    fontSize: 16,
    lineHeight: 24,
  },
  mono: {
    fontFamily: Fonts.mono,
    fontSize: 13,
    lineHeight: 20,
  },
});
