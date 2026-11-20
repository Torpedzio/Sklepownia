import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { TextField } from '@/components/ui/text-field';
import { Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { api, ApiError } from '@/lib/api';
import type { ProductDetail } from '@/lib/types';

const MAX_STOCK = 999_999;

/** Pieces in stock, set in the shop; `onChanged` gets the product read again afterwards. */
export function StockEditor({
  shopId,
  product,
  onChanged,
}: {
  shopId: string;
  product: ProductDetail;
  onChanged: (product: ProductDetail) => void;
}) {
  const notify = useNotify();
  const [value, setValue] = useState(product.stock === null ? '' : String(product.stock));
  const [error, setError] = useState<string>();
  const [saving, setSaving] = useState(false);

  if (product.has_variants) {
    return (
      <ThemedText type="small" themeColor="textSecondary">
        Ten produkt ma warianty albo składa się z innych produktów, więc każdy z nich ma własny stan. Zmienisz je na
        razie w panelu sklepu.
      </ThemedText>
    );
  }

  const quantity = /^\d+$/.test(value.trim()) ? Number(value.trim()) : null;
  const changed = quantity !== null && quantity !== product.stock;
  const step = (by: number) => {
    const next = Math.min(Math.max((quantity ?? product.stock ?? 0) + by, 0), MAX_STOCK);
    setValue(String(next));
    setError(undefined);
  };

  async function save() {
    if (quantity === null || quantity > MAX_STOCK) {
      setError(`Wpisz liczbę sztuk od 0 do ${MAX_STOCK.toLocaleString('pl-PL')}.`);
      return;
    }
    setSaving(true);
    try {
      const saved = await api<ProductDetail>(`/shops/${shopId}/products/${product.external_id}/stock/`, {
        method: 'POST',
        body: { quantity },
      });
      notify.success(saved.stock === 0 ? 'Zapisane: produktu brak w magazynie.' : `Zapisane: ${saved.stock} szt.`);
      setValue(saved.stock === null ? '' : String(saved.stock));
      onChanged(saved);
    } catch (e) {
      const fieldError = e instanceof ApiError ? e.fieldErrors.quantity : undefined;
      if (fieldError) setError(fieldError);
      else notify.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={styles.editor}>
      <ThemedText type="small" themeColor="textSecondary">
        {product.stock === null
          ? 'Sklep nie liczy sztuk tego produktu i sprzedaje go bez ograniczeń. Gdy zapiszesz stan, zacznie liczyć.'
          : 'Przy 0 sztuk sklep przestaje sprzedawać produkt, a gdy dopiszesz sztuki, znów go sprzedaje.'}
      </ThemedText>
      <View style={styles.row}>
        <Button
          title="−"
          variant="secondary"
          accessibilityLabel="Odejmij sztukę"
          disabled={saving || (quantity ?? product.stock ?? 0) <= 0}
          onPress={() => step(-1)}
        />
        <View style={styles.field}>
          <TextField
            label="Sztuk w magazynie"
            value={value}
            onChangeText={(text) => {
              setValue(text.replace(/[^\d]/g, ''));
              setError(undefined);
            }}
            error={error}
            keyboardType="number-pad"
            maxLength={6}
            placeholder="np. 10"
          />
        </View>
        <Button
          title="+"
          variant="secondary"
          accessibilityLabel="Dodaj sztukę"
          disabled={saving}
          onPress={() => step(1)}
        />
      </View>
      <Button title="Zapisz stan" loading={saving} disabled={!changed} onPress={save} style={styles.start} />
    </View>
  );
}

const styles = StyleSheet.create({
  editor: {
    gap: Spacing.three,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: Spacing.two,
  },
  field: {
    flex: 1,
    maxWidth: 200,
  },
  start: {
    alignSelf: 'flex-start',
  },
});
