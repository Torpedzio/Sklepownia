import { StyleSheet, View } from 'react-native';

import { ChipSelect } from '@/components/ui/chip-select';
import { TextField } from '@/components/ui/text-field';
import { Spacing } from '@/constants/theme';
import type { BillingProfile } from '@/lib/types';

// The same countries the platform sells shops for (shops.choices.Country).
const COUNTRIES = [
  { value: 'PL', label: 'Polska' },
  { value: 'DE', label: 'Niemcy' },
  { value: 'CZ', label: 'Czechy' },
  { value: 'SK', label: 'Słowacja' },
  { value: 'GB', label: 'Wielka Brytania' },
  { value: 'US', label: 'Stany Zjednoczone' },
];
const KINDS = [
  { value: 'individual', label: 'Osoba prywatna' },
  { value: 'company', label: 'Firma' },
];

export const EMPTY_PROFILE: BillingProfile = {
  kind: 'individual',
  full_name: '',
  company_name: '',
  tax_id: '',
  street: '',
  postal_code: '',
  city: '',
  country: 'PL',
};

type BillingProfileFormProps = {
  value: BillingProfile;
  onChange: (value: BillingProfile) => void;
  errors?: Record<string, string>;
};

export function BillingProfileForm({ value, onChange, errors = {} }: BillingProfileFormProps) {
  const company = value.kind === 'company';
  const polish = value.country === 'PL';
  const set = (field: keyof BillingProfile) => (text: string) => onChange({ ...value, [field]: text });

  return (
    <View style={styles.form}>
      <ChipSelect
        label="Kto płaci?"
        options={KINDS}
        value={value.kind}
        onChange={(kind) => onChange({ ...value, kind: kind as BillingProfile['kind'] })}
        error={errors.kind}
      />
      {company ? (
        <>
          <TextField
            label="Nazwa firmy"
            value={value.company_name}
            onChangeText={set('company_name')}
            error={errors.company_name}
            autoComplete="organization"
          />
          <TextField
            label={polish ? 'NIP' : 'Numer VAT'}
            value={value.tax_id}
            onChangeText={set('tax_id')}
            error={errors.tax_id}
            placeholder={polish ? '10 cyfr' : undefined}
            autoCapitalize="characters"
            autoCorrect={false}
            style={styles.short}
          />
        </>
      ) : null}
      <TextField
        label={company ? 'Osoba do kontaktu' : 'Imię i nazwisko'}
        value={value.full_name}
        onChangeText={set('full_name')}
        error={errors.full_name}
        autoComplete="name"
      />
      <TextField
        label="Ulica i numer"
        value={value.street}
        onChangeText={set('street')}
        error={errors.street}
        autoComplete="street-address"
      />
      <View style={styles.row}>
        <View style={styles.postal}>
          <TextField
            label="Kod pocztowy"
            value={value.postal_code}
            onChangeText={set('postal_code')}
            error={errors.postal_code}
            placeholder={polish ? '00-000' : undefined}
            autoComplete="postal-code"
          />
        </View>
        <View style={styles.city}>
          <TextField label="Miejscowość" value={value.city} onChangeText={set('city')} error={errors.city} />
        </View>
      </View>
      <ChipSelect
        label="Kraj"
        options={COUNTRIES}
        value={value.country}
        onChange={(country) => onChange({ ...value, country })}
        error={errors.country}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  form: {
    gap: Spacing.three,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
  postal: {
    flexBasis: 140,
    flexGrow: 0,
  },
  city: {
    flexBasis: 200,
    flexGrow: 1,
  },
  short: {
    maxWidth: 240,
  },
});
