import { StyleSheet, View } from 'react-native';

import { Note } from '@/components/ui/note';
import { SwitchRow } from '@/components/ui/switch-row';
import { TextField } from '@/components/ui/text-field';
import { Spacing } from '@/constants/theme';
import type { PaymentOperator, ShopSettingsValues } from '@/lib/types';

type Payments = ShopSettingsValues['payments'];

type Field = { field: string; label: string; hint?: string; placeholder?: string };

type Operator = {
  name: string;
  description: string;
  /** Identify the owner's account; kept in the settings. */
  ids: Field[];
  /** Sign the payments; sent to the shop, never shown again. */
  keys: Field[];
  where: string;
};

const OPERATORS: Record<PaymentOperator, Operator> = {
  przelewy24: {
    name: 'Przelewy24',
    description: 'BLIK, szybkie przelewy i karty na stronie Przelewy24. Potrzebujesz konta sprzedawcy w Przelewy24.',
    ids: [{ field: 'przelewy24_merchant_id', label: 'ID sprzedawcy', hint: 'Twój login do panelu Przelewy24.' }],
    keys: [
      { field: 'przelewy24_crc_key', label: 'Klucz CRC', placeholder: '16 znaków' },
      { field: 'przelewy24_api_key', label: 'Klucz API', placeholder: '32 znaki' },
    ],
    where: 'Klucz CRC i klucz API znajdziesz w panelu Przelewy24: Moje konto → Konfiguracja API.',
  },
  payu: {
    name: 'PayU',
    description: 'BLIK, szybkie przelewy i karty na stronie PayU. Potrzebujesz konta sprzedawcy w PayU.',
    ids: [
      { field: 'payu_pos_id', label: 'Id punktu płatności (pos_id)' },
      { field: 'payu_client_id', label: 'client_id (OAuth)', hint: 'Zwykle taki sam jak id punktu płatności.' },
    ],
    keys: [
      { field: 'payu_md5_key', label: 'Drugi klucz (MD5)', placeholder: '32 znaki' },
      { field: 'payu_client_secret', label: 'client_secret (OAuth)', placeholder: '32 znaki' },
    ],
    where: 'Wszystkie dane znajdziesz w panelu PayU, w punkcie płatności sklepu, w sekcji „Klucze konfiguracji”.',
  },
};

type Props = {
  operator: PaymentOperator;
  saved: Payments;
  value: (field: string) => string | boolean;
  onChange: (field: string, value: string | boolean) => void;
  error: (field: string) => string | undefined;
  /** For Przelewy24's list of allowed addresses. */
  serverIp: string | null;
};

export function OnlinePayment({ operator, saved, value, onChange, error, serverIp }: Props) {
  const info = OPERATORS[operator];
  const enabled = value(`${operator}_enabled`) === true;
  const sandbox = value(`${operator}_sandbox`) === true;
  // The shop's keys belong to the saved mode; a new mode needs its own.
  const keysSaved = saved[`${operator}_keys_saved`] && sandbox === saved[`${operator}_sandbox`];

  return (
    <View style={styles.operator}>
      <SwitchRow
        label={info.name}
        description={info.description}
        value={enabled}
        onChange={(next) => onChange(`${operator}_enabled`, next)}
        error={error(`${operator}_enabled`)}
      />
      {enabled ? (
        <View style={styles.nested}>
          <SwitchRow
            label="Tryb testowy"
            description={
              sandbox
                ? `Płatności na próbę, bez prawdziwych pieniędzy. Wpisz dane z konta testowego (sandbox) ${info.name}.`
                : 'Klienci płacą naprawdę. Włącz, żeby najpierw sprawdzić płatności na koncie testowym.'
            }
            value={sandbox}
            onChange={(next) => onChange(`${operator}_sandbox`, next)}
          />
          {info.ids.map(({ field, label, hint }) => (
            <TextField
              key={field}
              label={label}
              hint={hint}
              value={String(value(field) ?? '')}
              onChangeText={(text) => onChange(field, text)}
              error={error(field)}
              keyboardType="number-pad"
              autoCorrect={false}
              style={styles.short}
            />
          ))}
          {info.keys.map(({ field, label, placeholder }) => (
            <TextField
              key={field}
              label={label}
              hint={keysSaved ? 'Zapisany w sklepie. Wpisz nowy tylko, jeśli chcesz go zmienić.' : undefined}
              placeholder={keysSaved ? '••••••••' : placeholder}
              value={String(value(field) ?? '')}
              onChangeText={(text) => onChange(field, text)}
              error={error(field)}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="off"
            />
          ))}
          <Note>{info.where}</Note>
          {operator === 'przelewy24' ? (
            <Note>
              {serverIp
                ? `Przelewy24 przyjmuje płatności tylko ze znanych serwerów. W panelu Przelewy24 (Moje konto → ` +
                  `Konfiguracja API) dodaj adres IP serwera sklepu: ${serverIp}.`
                : 'Przelewy24 przyjmuje płatności tylko ze znanych serwerów. Napisz do nas, a podamy adres IP ' +
                  'serwera Twojego sklepu do wpisania w panelu Przelewy24.'}
            </Note>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  operator: {
    gap: Spacing.three,
  },
  nested: {
    gap: Spacing.three,
    paddingLeft: Spacing.three,
  },
  short: {
    maxWidth: 240,
  },
});
