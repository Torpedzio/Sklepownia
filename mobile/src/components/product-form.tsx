import { useState, type ReactNode } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { ChipMultiSelect } from '@/components/ui/chip-select';
import { Note } from '@/components/ui/note';
import { SwitchRow } from '@/components/ui/switch-row';
import { TextField } from '@/components/ui/text-field';
import { Radius, Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api, ApiError } from '@/lib/api';
import { currencySymbol } from '@/lib/format';
import type { Platform, ProductCategories, ProductDetail, ProductFields } from '@/lib/types';

const MAX_STOCK = 999_999;
// Up to 99 999 999,99, with a comma or a dot.
const PRICE = /^\d{1,8}([.,]\d{1,2})?$/;

type Form = {
  name: string;
  price: string;
  sale_price: string;
  sku: string;
  description: string;
  categories: string[];
  visible: boolean;
  stock: string;
};

function initialForm(product?: ProductDetail): Form {
  if (!product) {
    return { name: '', price: '', sale_price: '', sku: '', description: '', categories: [], visible: true, stock: '' };
  }
  const onSale = product.regular_price !== null;
  // As typed in Poland: "49,99".
  const typed = (amount: string | null) => (amount ?? '').replace('.', ',');
  return {
    name: product.name,
    price: typed(onSale ? product.regular_price : product.price),
    sale_price: onSale ? typed(product.price) : '',
    sku: product.sku,
    description: product.description,
    categories: product.categories.map((category) => category.id),
    visible: product.visible,
    stock: '',
  };
}

const price = (value: string) => value.trim().replace(/\s/g, '').replace(',', '.');

/**
 * A product's name, prices, description, categories and visibility; with `product` it changes that one (sending only
 * what was edited), without it adds a simple product. `onSaved` gets the product as the shop has it afterwards.
 */
export function ProductForm({
  shopId,
  platform,
  currency,
  product,
  onSaved,
}: {
  shopId: string;
  platform?: Platform;
  currency: string;
  product?: ProductDetail;
  onSaved: (product: ProductDetail) => void;
}) {
  const notify = useNotify();
  const [initial] = useState(() => initialForm(product));
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const categories = useApiQuery<ProductCategories>(`/shops/${shopId}/products/categories/`);
  const pricesLocked = !!product?.has_variants;
  const symbol = currencySymbol(currency);

  function update<K extends keyof Form>(key: K, value: Form[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setErrors(({ [key]: _, ...rest }) => rest);
  }

  function check() {
    const found: Record<string, string> = {};
    if (!form.name.trim()) found.name = 'Podaj nazwę produktu.';
    if (!pricesLocked) {
      if (!PRICE.test(price(form.price))) found.price = 'Wpisz cenę, np. 49,99.';
      if (form.sale_price.trim()) {
        if (!PRICE.test(price(form.sale_price))) found.sale_price = 'Wpisz cenę, np. 39,99, albo zostaw puste.';
        else if (!found.price && Number(price(form.sale_price)) >= Number(price(form.price))) {
          found.sale_price = 'Cena promocyjna musi być niższa od ceny.';
        }
      }
    }
    if (form.stock.trim() && !(/^\d+$/.test(form.stock.trim()) && Number(form.stock) <= MAX_STOCK)) {
      found.stock = `Wpisz liczbę sztuk od 0 do ${MAX_STOCK.toLocaleString('pl-PL')} albo zostaw puste.`;
    }
    return found;
  }

  function body(): Partial<ProductFields> {
    const all: ProductFields = {
      name: form.name.trim(),
      price: price(form.price),
      sale_price: form.sale_price.trim() ? price(form.sale_price) : null,
      sku: form.sku.trim(),
      description: form.description.trim(),
      categories: form.categories,
      visible: form.visible,
    };
    if (!product) return { ...all, stock: form.stock.trim() ? Number(form.stock) : null };
    // Only what was edited: a description with formatting stays as it is in the shop unless it was changed.
    const before: ProductFields = {
      name: initial.name,
      price: price(initial.price),
      sale_price: initial.sale_price ? price(initial.sale_price) : null,
      sku: initial.sku,
      description: initial.description,
      categories: initial.categories,
      visible: initial.visible,
    };
    const changed: Partial<ProductFields> = {};
    for (const key of Object.keys(all) as (keyof ProductFields)[]) {
      if (pricesLocked && (key === 'price' || key === 'sale_price')) continue;
      const same =
        key === 'price' || key === 'sale_price'
          ? (all[key] === null ? null : Number(all[key])) === (before[key] === null ? null : Number(before[key]))
          : JSON.stringify(all[key]) === JSON.stringify(before[key]);
      if (!same) Object.assign(changed, { [key]: all[key] });
    }
    return changed;
  }

  async function save() {
    const found = check();
    setErrors(found);
    if (Object.keys(found).length) return;
    const changes = body();
    if (product && !Object.keys(changes).length) {
      notify.success('Nic się nie zmieniło.');
      onSaved(product);
      return;
    }
    setSaving(true);
    try {
      const saved = await api<ProductDetail>(
        product ? `/shops/${shopId}/products/${product.external_id}/` : `/shops/${shopId}/products/`,
        { method: product ? 'PATCH' : 'POST', body: changes },
      );
      notify.success(product ? 'Zapisane w sklepie.' : `Dodane: „${saved.name}”.`);
      onSaved(saved);
    } catch (e) {
      // Field messages sit under the fields; the bar also covers fields scrolled out of view.
      if (e instanceof ApiError) setErrors(e.fieldErrors);
      notify.error((e as Error).message);
      setSaving(false);
    }
  }

  const options = (categories.data?.categories ?? []).map((category) => ({
    value: category.id,
    label: category.name,
  }));

  return (
    <View style={styles.form}>
      <Section title="Nazwa i cena">
        <TextField
          label="Nazwa"
          value={form.name}
          onChangeText={(name) => update('name', name)}
          error={errors.name}
          maxLength={200}
          placeholder="np. Kubek ceramiczny"
        />
        {pricesLocked ? (
          <Note>
            Ten produkt ma warianty z własnymi cenami. Zmienisz je na razie w panelu sklepu.
          </Note>
        ) : (
          <View style={styles.prices}>
            <View style={styles.price}>
              <TextField
                label={`Cena brutto (${symbol})`}
                value={form.price}
                onChangeText={(value) => update('price', value)}
                error={errors.price}
                keyboardType="decimal-pad"
                placeholder="49,99"
              />
            </View>
            <View style={styles.price}>
              <TextField
                label={`Cena promocyjna (${symbol})`}
                value={form.sale_price}
                onChangeText={(value) => update('sale_price', value)}
                error={errors.sale_price}
                hint="Puste: bez promocji."
                keyboardType="decimal-pad"
                placeholder="39,99"
              />
            </View>
          </View>
        )}
        {product ? null : (
          <TextField
            label="Sztuk w magazynie"
            value={form.stock}
            onChangeText={(value) => update('stock', value.replace(/[^\d]/g, ''))}
            error={errors.stock}
            hint={
              platform === 'woocommerce'
                ? 'Puste: sklep nie liczy sztuk i sprzedaje bez ograniczeń.'
                : 'Puste: 0 sztuk. Sklep sprzeda produkt, gdy dopiszesz sztuki.'
            }
            keyboardType="number-pad"
            maxLength={6}
            placeholder="np. 10"
          />
        )}
        <TextField
          label="SKU (kod produktu)"
          value={form.sku}
          onChangeText={(value) => update('sku', value)}
          error={errors.sku}
          hint={
            !product && platform === 'magento' ? 'Puste: utworzymy go z nazwy.' : 'Nieobowiązkowy, Twój kod do magazynu.'
          }
          maxLength={64}
          autoCapitalize="characters"
          autoCorrect={false}
        />
      </Section>

      <Section title="Opis">
        {product?.formatted_description ? (
          <Note warning>
            Opis w sklepie ma formatowanie, np. listy albo pogrubienia. Tutaj widzisz sam tekst. Jeśli go zmienisz,
            zapiszemy go bez formatowania. Jeśli go nie ruszysz, formatowanie zostanie.
          </Note>
        ) : null}
        <TextField
          label="Opis produktu"
          value={form.description}
          onChangeText={(value) => update('description', value)}
          error={errors.description}
          hint="Pusta linia zaczyna nowy akapit."
          multiline
          maxLength={20000}
          placeholder="Z czego jest, jak go używać, co jest w zestawie…"
        />
      </Section>

      <Section title="Kategorie i widoczność">
        {categories.data ? (
          options.length ? (
            <ChipMultiSelect
              label="Kategorie"
              options={options}
              values={form.categories}
              onChange={(values) => update('categories', values)}
              hint={
                form.categories.length > 1
                  ? `Główna: ${options.find((option) => option.value === form.categories[0])?.label ?? 'pierwsza wybrana'} (wybrana jako pierwsza).`
                  : undefined
              }
              error={errors.categories}
            />
          ) : (
            <ThemedText type="small" themeColor="textSecondary">
              Sklep nie ma jeszcze kategorii. Dodasz je w panelu sklepu.
            </ThemedText>
          )
        ) : categories.error ? (
          <View style={styles.inline}>
            <ThemedText type="small" themeColor="danger">
              {categories.error.message}
            </ThemedText>
            <Button title="Wczytaj kategorie" variant="secondary" icon="refresh" onPress={categories.refresh} />
          </View>
        ) : (
          <ActivityIndicator style={styles.start} />
        )}
        <SwitchRow
          label="Widoczny w sklepie"
          description="Wyłączony: klienci go nie znajdą ani nie kupią."
          value={form.visible}
          onChange={(visible) => update('visible', visible)}
          error={errors.visible}
        />
      </Section>

      <Button
        title={product ? 'Zapisz zmiany' : 'Dodaj produkt'}
        size="large"
        loading={saving}
        onPress={save}
        style={styles.start}
      />
    </View>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  const theme = useTheme();
  return (
    <View style={[styles.section, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <ThemedText type="heading">{title}</ThemedText>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  form: {
    gap: Spacing.four,
  },
  section: {
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  prices: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
  price: {
    flexGrow: 1,
    flexBasis: 160,
  },
  inline: {
    gap: Spacing.two,
    alignItems: 'flex-start',
  },
  start: {
    alignSelf: 'flex-start',
  },
});
