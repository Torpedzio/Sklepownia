import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { TextField } from '@/components/ui/text-field';
import { Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { api, ApiError } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import type { OrderAction, Platform, ShopOrderDetail } from '@/lib/types';

const DONE: Record<OrderAction, string> = {
  mark_paid: 'Zamówienie oznaczone jako opłacone.',
  mark_shipped: 'Zamówienie oznaczone jako wysłane.',
  cancel: 'Zamówienie anulowane.',
};

/** The changes the order can take now, done in the shop; `onChanged` gets the order read again afterwards. */
export function OrderActions({
  shopId,
  order,
  platform,
  onChanged,
}: {
  shopId: string;
  order: ShopOrderDetail;
  platform: Platform | undefined;
  onChanged: (order: ShopOrderDetail) => void;
}) {
  const notify = useNotify();
  const [busy, setBusy] = useState<OrderAction>();
  const [shipping, setShipping] = useState(false);
  const [trackingNumber, setTrackingNumber] = useState('');
  const [carrier, setCarrier] = useState('');
  const [errors, setErrors] = useState<{ tracking_number?: string; carrier?: string }>({});
  const can = (action: OrderAction) => order.actions.includes(action);
  // PrestaShop sends the parcel with the carrier the customer chose, and its "shipped" e-mail has no parcel number.
  const asksCarrier = platform !== 'prestashop';

  async function run(action: OrderAction, fields: Record<string, string> = {}) {
    setBusy(action);
    setErrors({});
    try {
      const changed = await api<ShopOrderDetail>(`/shops/${shopId}/orders/${order.external_id}/actions/`, {
        method: 'POST',
        body: { action, ...fields },
      });
      notify.success(DONE[action]);
      setShipping(false);
      setTrackingNumber('');
      setCarrier('');
      onChanged(changed);
    } catch (e) {
      const fieldErrors = e instanceof ApiError ? e.fieldErrors : {};
      if (fieldErrors.tracking_number || fieldErrors.carrier) setErrors(fieldErrors);
      else notify.error((e as Error).message);
    } finally {
      setBusy(undefined);
    }
  }

  async function markPaid() {
    const confirmed = await confirm(
      'Oznaczyć jako opłacone?',
      `Zamówienie nr ${order.number} przejdzie do realizacji, a sklep może wysłać klientowi e-mail.`,
      'Oznacz jako opłacone',
    );
    if (confirmed) await run('mark_paid');
  }

  async function cancel() {
    const confirmed = await confirm(
      'Anulować zamówienie?',
      `Sklep anuluje zamówienie nr ${order.number}. Zwrot pieniędzy, jeśli klient już zapłacił, zrobisz u operatora płatności.`,
      'Anuluj zamówienie',
      'Nie anuluj',
    );
    if (confirmed) await run('cancel');
  }

  if (!order.actions.length) {
    return (
      <ThemedText type="small" themeColor="textSecondary">
        {order.status === 'completed' || order.status === 'cancelled'
          ? 'To zamówienie jest zamknięte. Nic tu już nie trzeba robić.'
          : 'Tego zamówienia nie da się już zmienić w aplikacji. Zrobisz to w panelu sklepu.'}
      </ThemedText>
    );
  }

  if (shipping) {
    return (
      <View style={styles.form}>
        <TextField
          label="Numer przesyłki"
          hint={
            asksCarrier
              ? 'Nieobowiązkowy. Klient dostanie go w wiadomości ze sklepu.'
              : 'Nieobowiązkowy. Klient zobaczy go w szczegółach zamówienia w sklepie.'
          }
          value={trackingNumber}
          onChangeText={setTrackingNumber}
          error={errors.tracking_number}
          autoCapitalize="characters"
          autoCorrect={false}
          maxLength={60}
        />
        {asksCarrier ? (
          <TextField
            label="Przewoźnik"
            hint="Np. InPost albo DPD, żeby klient wiedział, gdzie śledzić paczkę."
            value={carrier}
            onChangeText={setCarrier}
            error={errors.carrier}
            maxLength={60}
          />
        ) : null}
        <View style={styles.row}>
          <Button
            title="Oznacz jako wysłane"
            icon="truck"
            loading={busy === 'mark_shipped'}
            onPress={() => run('mark_shipped', { tracking_number: trackingNumber, carrier })}
          />
          <Button title="Wróć" variant="ghost" disabled={!!busy} onPress={() => setShipping(false)} />
        </View>
      </View>
    );
  }

  const open = order.status === 'new' || order.status === 'processing';

  return (
    <View style={styles.form}>
      <View style={styles.row}>
        {can('mark_shipped') ? (
          <Button title="Oznacz jako wysłane" icon="truck" disabled={!!busy} onPress={() => setShipping(true)} />
        ) : null}
        {can('mark_paid') ? (
          <Button
            title="Oznacz jako opłacone"
            icon="card"
            variant="secondary"
            loading={busy === 'mark_paid'}
            disabled={!!busy}
            onPress={markPaid}
          />
        ) : null}
        {can('cancel') ? (
          <Button
            title="Anuluj zamówienie"
            variant="danger"
            loading={busy === 'cancel'}
            disabled={!!busy}
            onPress={cancel}
          />
        ) : null}
      </View>
      {open && !can('cancel') ? (
        <ThemedText type="small" themeColor="textSecondary">
          Sklep ma już fakturę do tego zamówienia, więc anulujesz je, robiąc zwrot w panelu sklepu.
        </ThemedText>
      ) : null}
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
    gap: Spacing.two,
  },
});
