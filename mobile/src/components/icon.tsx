import { SymbolView, type SymbolViewProps } from 'expo-symbols';

import type { ThemeColor } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

// SF Symbols on iOS, Material Symbols on Android and web.
const ICONS = {
  store: ['storefront', 'storefront'],
  search: ['magnifyingglass', 'search'],
  category: ['square.grid.2x2', 'category'],
  filter: ['slider.horizontal.3', 'tune'],
  palette: ['paintpalette', 'palette'],
  admin: ['gearshape', 'settings'],
  clock: ['clock', 'schedule'],
  mail: ['envelope', 'mail'],
  phone: ['phone', 'call'],
  pin: ['mappin.and.ellipse', 'location_on'],
  help: ['questionmark.circle', 'help'],
  person: ['person.crop.circle', 'account_circle'],
  refresh: ['arrow.clockwise', 'refresh'],
  shield: ['lock.shield', 'shield'],
  plus: ['plus', 'add'],
  external: ['arrow.up.right', 'open_in_new'],
  check: ['checkmark', 'check'],
  warning: ['exclamationmark.triangle', 'warning'],
  close: ['xmark', 'close'],
  chevron: ['chevron.right', 'chevron_right'],
  chevronLeft: ['chevron.left', 'chevron_left'],
  pause: ['pause.fill', 'pause'],
  play: ['play.fill', 'play_arrow'],
  chevronDown: ['chevron.down', 'expand_more'],
  arrowUp: ['arrow.up', 'arrow_upward'],
  arrowDown: ['arrow.down', 'arrow_downward'],
  logout: ['rectangle.portrait.and.arrow.right', 'logout'],
  cart: ['cart', 'shopping_cart'],
  card: ['creditcard', 'credit_card'],
  truck: ['shippingbox', 'local_shipping'],
  percent: ['percent', 'percent'],
  globe: ['globe', 'language'],
  power: ['power', 'power_settings_new'],
  history: ['clock.arrow.circlepath', 'history'],
  backup: ['arrow.counterclockwise.circle', 'settings_backup_restore'],
  camera: ['camera.fill', 'photo_camera'],
  trash: ['trash', 'delete'],
  document: ['doc.text', 'description'],
  chart: ['chart.bar', 'bar_chart'],
  bell: ['bell', 'notifications'],
} as const;

export type IconName = keyof typeof ICONS;

type IconProps = { name: IconName; size?: number; color?: ThemeColor; tintColor?: string };

export function Icon({ name, size = 20, color = 'text', tintColor }: IconProps) {
  const theme = useTheme();
  const [ios, material] = ICONS[name];
  return (
    <SymbolView
      name={{ ios, android: material, web: material } as SymbolViewProps['name']}
      size={size}
      tintColor={tintColor ?? theme[color]}
    />
  );
}
