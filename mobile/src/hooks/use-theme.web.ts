import { WebColors, type ThemeColors } from '@/constants/theme';

/** CSS variables that follow the visitor's mode by themselves (see `WebColors`). */
export function useTheme(): ThemeColors {
  return WebColors;
}
