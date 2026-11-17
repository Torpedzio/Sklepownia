import { Link, Stack } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { Icon } from '@/components/icon';
import { Page } from '@/components/page';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { TextField } from '@/components/ui/text-field';
import { Radius, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { ApiError } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import type { BillingOverview, Shop } from '@/lib/types';

/** Says what goes with the account, offers cancelling the plan instead, and deletes after the password. */
export default function DeleteAccountScreen() {
  const { data: shops, error: shopsError } = useApiQuery<Shop[]>('/shops/');
  const { data: billing, error: billingError } = useApiQuery<BillingOverview>('/billing/');
  const problem = shopsError ?? billingError;

  return (
    <Page maxWidth={760}>
      <Stack.Screen options={{ title: 'Usuń konto', ...backArrowOptions('/account', 'Wróć do konta') }} />
      <View style={styles.intro}>
        <ThemedText type="title">Usuń konto</ThemedText>
        <ThemedText themeColor="textSecondary">Usunięcia nie da się cofnąć. Sprawdź, co zniknie.</ThemedText>
      </View>
      {problem ? <ThemedText themeColor="danger">{problem.message}</ThemedText> : null}
      {!problem && (!shops || !billing) ? <ActivityIndicator style={styles.loader} /> : null}
      {shops && billing ? <DeleteForm shops={shops} billing={billing} /> : null}
    </Page>
  );
}

function DeleteForm({ shops, billing }: { shops: Shop[]; billing: BillingOverview }) {
  const theme = useTheme();
  const notify = useNotify();
  const { user, deleteAccount } = useAuth();
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string>();
  const [deleting, setDeleting] = useState(false);
  const subscription = billing.subscription;
  const paying = !!subscription && ['active', 'past_due'].includes(subscription.status);
  const paid = billing.payments.some((payment) => payment.status === 'paid');
  const settingUp = shops.find((shop) => shop.status === 'pending' || shop.status === 'provisioning');

  async function handleDelete() {
    const confirmed = await confirm(
      'Usunąć konto na zawsze?',
      shops.length === 1
        ? `Sklep ${shops[0].name} zniknie od razu razem z danymi. Tego nie da się cofnąć.`
        : shops.length
          ? `Sklepy ${shops.map((shop) => shop.name).join(', ')} znikną od razu razem z danymi. Tego nie da się cofnąć.`
          : 'Tego nie da się cofnąć.',
      'Usuń konto',
    );
    if (!confirmed) return;
    const email = user?.email;
    setDeleting(true);
    setError(undefined);
    try {
      await deleteAccount(password);
      notify.success(`Konto usunięte. Potwierdzenie wysłaliśmy na ${email}.`);
    } catch (e) {
      const fieldError = e instanceof ApiError ? e.fieldErrors.password : undefined;
      setError(fieldError);
      notify.error(fieldError ? 'Popraw zaznaczone pola.' : (e as Error).message);
      setDeleting(false);
    }
  }

  return (
    <>
      <View style={[styles.card, { backgroundColor: theme.dangerMuted, borderColor: theme.danger }]}>
        <ThemedText type="heading">Co zniknie</ThemedText>
        {shops.length ? (
          <View style={styles.list}>
            <ThemedText>
              {shops.length === 1 ? 'Sklep' : 'Sklepy'} razem z produktami, zamówieniami i kontami klientów:
            </ThemedText>
            {shops.map((shop) => (
              <View key={shop.id} style={styles.shop}>
                <Icon name="trash" size={16} color="danger" />
                <ThemedText type="smallBold">{shop.name}</ThemedText>
                <ThemedText type="small" themeColor="textSecondary">
                  {shop.url.replace(/^https?:\/\//, '')}
                </ThemedText>
              </View>
            ))}
          </View>
        ) : (
          <ThemedText>Nie masz sklepów, więc żaden nie zniknie.</ThemedText>
        )}
        {paying ? (
          <ThemedText>
            Plan {subscription.plan.name} przestanie działać od razu i nie pobierzemy już żadnej płatności. Za resztę
            opłaconego okresu nie ma automatycznego zwrotu. Jeśli go chcesz,{' '}
            <Link href="/contact">
              <ThemedText type="link">napisz do nas</ThemedText>
            </Link>{' '}
            przed usunięciem konta.
          </ThemedText>
        ) : null}
        <ThemedText>Dane konta, zdjęcie profilowe, zapisana karta i dane do faktury.</ThemedText>
      </View>

      <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
        <ThemedText type="heading">Co zostanie</ThemedText>
        <ThemedText themeColor="textSecondary">
          {paid
            ? 'Opłacone płatności z danymi z faktur, bo przepisy podatkowe każą je przechowywać. Twój adres e-mail nie będzie już z nimi powiązany. '
            : 'Nic, co by Cię identyfikowało. '}
          Na ten sam adres założysz nowe konto, jeśli zechcesz.
        </ThemedText>
      </View>

      {paying && !subscription.cancel_at_period_end ? (
        <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          <ThemedText type="heading">Chcesz tylko przestać płacić?</ThemedText>
          <ThemedText themeColor="textSecondary">
            Anuluj plan. Sklepy będą działać do końca opłaconego okresu, a konto zostanie.
          </ThemedText>
          <Link href="/billing" asChild>
            <Button title="Przejdź do planu i płatności" variant="secondary" icon="card" style={styles.alternative} />
          </Link>
        </View>
      ) : null}

      {settingUp ? (
        <ThemedText themeColor="danger">
          Sklep „{settingUp.name}” jest właśnie zakładany. Poczekaj, aż będzie gotowy, i wtedy usuń konto.
        </ThemedText>
      ) : null}
      <TextField
        label="Hasło"
        value={password}
        onChangeText={(text) => {
          setPassword(text);
          setError(undefined);
        }}
        error={error}
        hint="Wpisz hasło, żeby potwierdzić, że to Ty."
        secureTextEntry
        autoComplete="current-password"
        textContentType="password"
      />
      <Button
        title="Usuń konto na zawsze"
        variant="danger"
        icon="trash"
        size="large"
        loading={deleting}
        disabled={!password || !!settingUp}
        onPress={handleDelete}
      />
    </>
  );
}

const styles = StyleSheet.create({
  intro: {
    gap: Spacing.two,
  },
  loader: {
    marginVertical: Spacing.four,
  },
  card: {
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1.5,
  },
  list: {
    gap: Spacing.two,
  },
  shop: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: Spacing.two,
  },
  alternative: {
    alignSelf: 'flex-start',
  },
});
