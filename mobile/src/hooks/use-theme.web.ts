import { WebColors, type ThemeColors } from '@/constants/theme';

/** CSS variables that follow the visitor's light or dark mode by themselves (see `WebColors`). */
export function useTheme(): ThemeColors {
  return WebColors;
}
