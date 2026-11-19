import { router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { Icon, type IconName } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Choice, SettingsSection, ShopSettings } from '@/lib/types';

export type Tile = {
  /** The section the tile shows. */
  key: SettingsSection;
  /** The section it opens, as in the address: ?section=…. */
  section: string;
  title: string;
  icon: IconName;
  value: string;
  /** Customers can't buy until this is set. */
  missing?: boolean;
};

export function ShopOverview({ shopId, settings }: { shopId: number; settings: ShopSettings }) {
  const tiles = describeSettings(settings);
  return (
    <View style={styles.grid}>
      {tiles.map((tile) => (
        <OverviewTile
          key={tile.section}
          tile={tile}
          onPress={() =>
            router.push({ pathname: '/shops/[id]/settings', params: { id: String(shopId), section: tile.section } })
          }
        />
      ))}
    </View>
  );
}

export function missingForSales(settings: ShopSettings) {
  const { values } = settings;
  const missing: string[] = [];
  if (supports(settings, 'payments') && !paymentMethods(values.payments).length) missing.push('płatności');
  if (supports(settings, 'shipping') && !hasShipping(values.shipping)) missing.push('wysyłkę');
  return missing;
}

function paymentMethods(payments: ShopSettings['values']['payments']) {
  return [
    payments.bank_transfer_enabled && 'przelew tradycyjny',
    payments.cash_on_delivery_enabled && 'płatność przy odbiorze',
    payments.przelewy24_enabled && 'Przelewy24',
    payments.payu_enabled && 'PayU',
  ].filter((method): method is string => Boolean(method));
}

/** Whether the app can change `section` on this platform; the rest is set in the shop's panel. */
export function supports(settings: Pick<ShopSettings, 'sections'>, section: SettingsSection) {
  return !settings.sections || settings.sections.includes(section);
}

function OverviewTile({ tile, onPress }: { tile: Tile; onPress: () => void }) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${tile.title}: ${tile.value.replace(/\.$/, '')}. Zmień w ustawieniach.`}
      onPress={onPress}
      style={({ hovered, pressed }) => [
        styles.tile,
        {
          backgroundColor: hovered || pressed ? theme.surfaceMuted : theme.surface,
          borderColor: tile.missing ? theme.accent : theme.border,
        },
      ]}>
      <View style={styles.tileHeader}>
        <Icon
          name={tile.missing ? 'warning' : tile.icon}
          size={18}
          tintColor={tile.missing ? theme.warning : undefined}
        />
        <ThemedText type="smallBold" style={styles.flex}>
          {tile.title}
        </ThemedText>
        <Icon name="chevron" size={16} color="textSecondary" />
      </View>
      <ThemedText type="small" themeColor={tile.missing ? 'text' : 'textSecondary'}>
        {tile.value}
      </ThemedText>
    </Pressable>
  );
}

export function describeSettings(settings: ShopSettings): Tile[] {
  return allTiles(settings).filter((tile) => supports(settings, tile.key));
}

function allTiles({ values, options }: ShopSettings): Tile[] {
  const { payments, shipping, taxes, region } = values;
  const currency = region.currency;
  const label = (choices: Choice[], value: string) => choices.find((choice) => choice.value === value)?.label ?? value;
  const money = (amount: string) => `${amount.replace('.', ',')} ${currency}`;

  const methods = paymentMethods(payments);
  const freeFrom = Number(shipping.free_shipping_min_amount);
  const shippingMethods = [
    shipping.courier_enabled && `kurier ${money(shipping.courier_cost)}`,
    shipping.free_shipping_enabled &&
      (freeFrom > 0 ? `darmowa od ${money(shipping.free_shipping_min_amount)}` : 'zawsze darmowa'),
    shipping.local_pickup_enabled && 'odbiór osobisty',
  ].filter(Boolean);

  return [
    {
      key: 'availability',
      section: 'dostepnosc',
      title: 'Sklep',
      icon: 'power',
      value: values.availability.is_open
        ? 'Otwarty, przyjmuje zamówienia.'
        : 'Zamknięty. Klienci widzą stronę „Wkrótce otwarcie”.',
    },
    {
      key: 'payments',
      section: 'platnosci',
      title: 'Płatności',
      icon: 'card',
      value: methods.length ? capitalize(methods.join(', ')) : 'Brak. Klienci nie mają jak zapłacić.',
      missing: !methods.length,
    },
    {
      key: 'shipping',
      section: 'wysylka',
      title: 'Wysyłka',
      icon: 'truck',
      value: shippingMethods.length ? capitalize(shippingMethods.join(', ')) : 'Brak. Klienci nie wybiorą dostawy.',
      missing: !shippingMethods.length,
    },
    {
      key: 'shopping',
      section: 'zakupy',
      title: 'Zakupy',
      icon: 'cart',
      value: [
        values.shopping.guest_checkout ? 'Bez zakładania konta' : 'Tylko z kontem klienta',
        values.shopping.reviews ? 'opinie włączone' : 'bez opinii',
      ].join(', '),
    },
    {
      key: 'taxes',
      section: 'podatki',
      title: 'Podatki',
      icon: 'percent',
      value: taxes.enabled
        ? `VAT ${Number(taxes.standard_rate)}%, ceny ${taxes.prices_include_tax ? 'brutto' : 'netto'}`
        : 'Bez naliczania VAT',
    },
    {
      key: 'region',
      section: 'region',
      title: 'Region',
      icon: 'globe',
      value: `${label(options.languages, region.language)}, ${currency}, ${label(options.countries, region.country)}`,
    },
    {
      key: 'appearance',
      section: 'wyglad',
      title: 'Wygląd',
      icon: 'palette',
      value: `Motyw ${label(options.themes, values.appearance.theme)}`,
    },
    {
      key: 'general',
      section: 'podstawowe',
      title: 'Kontakt',
      icon: 'mail',
      value: values.general.contact_email,
    },
  ];
}

function hasShipping(shipping: ShopSettings['values']['shipping']) {
  return shipping.courier_enabled || shipping.free_shipping_enabled || shipping.local_pickup_enabled;
}

function capitalize(text: string) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
  tile: {
    flexBasis: 220,
    flexGrow: 1,
    gap: Spacing.one,
    padding: Spacing.three,
    borderRadius: Radius.medium,
    borderWidth: 1.5,
  },
  tileHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
});
