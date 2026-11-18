import { useState } from 'react';
import { Linking, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { ChipSelect } from '@/components/ui/chip-select';
import { Note } from '@/components/ui/note';
import { SwitchRow } from '@/components/ui/switch-row';
import { TextField } from '@/components/ui/text-field';
import { Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Choice, DocumentBlock, DocumentListItem, ShopDocument, ShopSettingsValues } from '@/lib/types';

type Documents = ShopSettingsValues['documents'];
type Field = keyof Documents & string;

type Props = {
  /** The documents' settings as saved. */
  saved: Documents;
  /** The value as edited, or the saved one. */
  value: <K extends Field>(field: K) => Documents[K];
  onChange: (field: Field, value: string | boolean) => void;
  error: (field: Field) => string | undefined;
  registers: Choice[];
  /** The country the shop sells from, as edited; the templates follow Polish law. */
  country: string;
  /** The documents as they'd be with the edits, or null when the edits need fixing first. */
  onPreview: () => Promise<ShopDocument[] | null>;
};

/** The body of the terms and privacy policy section of the shop settings. */
export function DocumentsSettings({ saved, value, onChange, error, registers, country, onPreview }: Props) {
  const theme = useTheme();
  const [preview, setPreview] = useState<ShopDocument[] | null>(null);
  const [shown, setShown] = useState<ShopDocument['key']>('terms');
  const [loading, setLoading] = useState(false);
  const managed = value('managed');
  const register = value('register');
  const polish = country === 'PL';
  const number = (field: 'return_days' | 'dispatch_days') => String(value(field));

  async function showPreview() {
    setLoading(true);
    try {
      const documents = await onPreview();
      if (documents) setPreview(documents);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <SwitchRow
        label="Regulamin i polityka prywatności z aplikacji"
        description={
          managed
            ? 'Aktualizujemy je same po każdej zmianie płatności, wysyłki, danych sklepu i sprzedawcy.'
            : 'Przygotujemy je z danych sklepu i opublikujemy jako strony w sklepie, z linkami w stopce.'
        }
        value={managed}
        onChange={(next) => onChange('managed', next)}
        disabled={!polish && !managed}
        error={error('managed')}
      />
      {!polish ? (
        <Note warning>Wzory są na razie dla sklepów sprzedających z Polski. Kraj sklepu zmienisz w sekcji Region.</Note>
      ) : null}
      {managed && !saved.managed ? (
        <Note warning>
          Obecny regulamin i politykę prywatności sklepu zastąpimy nowymi. Jeśli masz własne dokumenty od prawnika,
          zostaw tę opcję wyłączoną.
        </Note>
      ) : null}
      {!managed && saved.managed ? (
        <Note>Strony zostaną w sklepie, ale przestaniemy je aktualizować. Zmienisz je wtedy w panelu sklepu.</Note>
      ) : null}
      {saved.managed && saved.terms_url ? (
        <View style={styles.links}>
          <Button
            title="Regulamin w sklepie"
            icon="external"
            variant="ghost"
            onPress={() => Linking.openURL(saved.terms_url)}
          />
          <Button
            title="Polityka prywatności w sklepie"
            icon="external"
            variant="ghost"
            onPress={() => Linking.openURL(saved.privacy_url)}
          />
        </View>
      ) : null}

      <View style={[styles.subsection, { borderTopColor: theme.border }]}>
        <ThemedText type="heading">Sprzedawca</ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          Te dane klient zobaczy w regulaminie. Na start wzięliśmy je z Twoich danych do faktur.
        </ThemedText>
      </View>
      <TextField
        label="Nazwa sprzedawcy"
        hint="Pełna nazwa firmy, tak jak w rejestrze, albo imię i nazwisko."
        value={value('seller_name')}
        onChangeText={(text) => onChange('seller_name', text)}
        error={error('seller_name')}
      />
      <ChipSelect
        label="Forma działalności"
        options={registers}
        value={register}
        onChange={(next) => onChange('register', next)}
        error={error('register')}
      />
      <TextField
        label="Ulica i numer"
        value={value('street')}
        onChangeText={(text) => onChange('street', text)}
        error={error('street')}
        autoComplete="street-address"
      />
      <View style={styles.row}>
        <TextField
          label="Kod pocztowy"
          placeholder="00-000"
          value={value('postal_code')}
          onChangeText={(text) => onChange('postal_code', text)}
          error={error('postal_code')}
          keyboardType="numbers-and-punctuation"
          autoComplete="postal-code"
          style={styles.postalCode}
        />
        <View style={styles.flex}>
          <TextField
            label="Miejscowość"
            value={value('city')}
            onChangeText={(text) => onChange('city', text)}
            error={error('city')}
          />
        </View>
      </View>
      <TextField
        label={register === 'unregistered' ? 'NIP (opcjonalnie)' : 'NIP'}
        value={value('tax_id')}
        onChangeText={(text) => onChange('tax_id', text)}
        error={error('tax_id')}
        keyboardType="number-pad"
        style={styles.short}
      />
      {register === 'krs' ? (
        <TextField
          label="Numer KRS"
          placeholder="0000123456"
          value={value('krs')}
          onChangeText={(text) => onChange('krs', text)}
          error={error('krs')}
          keyboardType="number-pad"
          style={styles.short}
        />
      ) : null}
      {register !== 'unregistered' ? (
        <TextField
          label="REGON (opcjonalnie)"
          value={value('regon')}
          onChangeText={(text) => onChange('regon', text)}
          error={error('regon')}
          keyboardType="number-pad"
          style={styles.short}
        />
      ) : null}
      <TextField
        label="Telefon (opcjonalnie)"
        hint="Jeśli go podasz, klienci zobaczą go w dokumentach obok adresu e-mail sklepu."
        value={value('phone')}
        onChangeText={(text) => onChange('phone', text)}
        error={error('phone')}
        keyboardType="phone-pad"
        autoComplete="tel"
        style={styles.short}
      />

      <View style={[styles.subsection, { borderTopColor: theme.border }]}>
        <ThemedText type="heading">Zwroty i wysyłka</ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          Płatności i sposoby dostawy weźmiemy z ich sekcji ustawień.
        </ThemedText>
      </View>
      <TextField
        label="Dni na odstąpienie od umowy"
        hint="Klient ma ustawowo 14 dni na zwrot bez podania przyczyny. Możesz dać więcej."
        value={number('return_days')}
        onChangeText={(text) => onChange('return_days', text)}
        error={error('return_days')}
        keyboardType="number-pad"
        style={styles.short}
      />
      <SwitchRow
        label="Darmowy zwrot"
        description={
          value('free_returns') ? 'Pokrywasz koszt odesłania towaru.' : 'Klient sam płaci za odesłanie towaru.'
        }
        value={value('free_returns')}
        onChange={(next) => onChange('free_returns', next)}
      />
      <TextField
        label="Czas wysyłki (dni robocze)"
        hint="W ilu dniach roboczych od opłacenia zamówienia nadajesz paczkę."
        value={number('dispatch_days')}
        onChangeText={(text) => onChange('dispatch_days', text)}
        error={error('dispatch_days')}
        keyboardType="number-pad"
        style={styles.short}
      />

      <Note>
        Wzory przygotowaliśmy według polskiego prawa konsumenckiego i RODO, ale nie zastąpią porady prawnej. Jeśli
        sprzedajesz np. żywność, leki, usługi albo treści cyfrowe, pokaż dokumenty prawnikowi.
      </Note>
      <Button
        title={preview ? 'Odśwież podgląd' : 'Podgląd dokumentów'}
        icon="document"
        variant="secondary"
        loading={loading}
        onPress={showPreview}
        style={styles.start}
      />
      {preview ? (
        <View style={[styles.preview, { borderColor: theme.border, backgroundColor: theme.background }]}>
          <View style={styles.previewHeader}>
            <View style={styles.flex}>
              <ChipSelect
                label="Podgląd"
                options={preview.map((document) => ({
                  value: document.key,
                  label: document.title,
                }))}
                value={shown}
                onChange={(next) => setShown(next as ShopDocument['key'])}
              />
            </View>
            <Button title="Zamknij" icon="close" variant="ghost" onPress={() => setPreview(null)} />
          </View>
          <DocumentText blocks={(preview.find((document) => document.key === shown) ?? preview[0]).blocks} />
        </View>
      ) : null}
    </>
  );
}

/** A document's blocks as text: headings, paragraphs and lists. */
export function DocumentText({ blocks }: { blocks: DocumentBlock[] }) {
  return (
    <View style={styles.document}>
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          return (
            <ThemedText key={index} type="smallBold" accessibilityRole="header" style={styles.documentHeading}>
              {block.text}
            </ThemedText>
          );
        }
        if (block.type === 'paragraph') {
          return (
            <ThemedText key={index} type="small">
              {block.text}
            </ThemedText>
          );
        }
        return <DocumentList key={index} ordered={block.ordered} items={block.items} />;
      })}
    </View>
  );
}

function DocumentList({ ordered, items }: { ordered: boolean; items: DocumentListItem[] }) {
  return (
    <View style={styles.list}>
      {items.map((item, index) => (
        <View key={index} style={styles.listItem}>
          <ThemedText type="small" style={styles.marker}>
            {ordered ? `${index + 1}.` : '•'}
          </ThemedText>
          <View style={[styles.flex, styles.list]}>
            <ThemedText type="small">{item.text}</ThemedText>
            {item.items?.length ? <DocumentList ordered={ordered} items={item.items} /> : null}
          </View>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
  short: {
    maxWidth: 200,
  },
  postalCode: {
    width: 120,
  },
  subsection: {
    gap: Spacing.one,
    paddingTop: Spacing.three,
    borderTopWidth: 1,
  },
  links: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
  },
  start: {
    alignSelf: 'flex-start',
  },
  preview: {
    gap: Spacing.three,
    padding: Spacing.three,
    borderRadius: Radius.medium,
    borderWidth: 1,
  },
  previewHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: Spacing.two,
  },
  document: {
    gap: Spacing.two,
  },
  documentHeading: {
    marginTop: Spacing.two,
  },
  list: {
    gap: Spacing.one,
  },
  listItem: {
    flexDirection: 'row',
    gap: Spacing.two,
  },
  marker: {
    minWidth: 18,
  },
});
