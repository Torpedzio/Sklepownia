import { Link, Redirect, useLocalSearchParams } from 'expo-router';
import { useEffect } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { Icon } from '@/components/icon';
import { Page } from '@/components/page';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { formatDate } from '@/lib/format';
import type { Payment } from '@/lib/types';

const POLL_MS = 2000;

/** Where the payment gateway sends the payer back. Waits for the payment's outcome. */
export default function PaymentReturnScreen() {
  const { payment: paymentId } = useLocalSearchParams<{ payment?: string }>();
  if (!paymentId || !/^\d+$/.test(paymentId)) return <Redirect href="/billing" />;
  return <PaymentOutcome paymentId={paymentId} />;
}

function PaymentOutcome({ paymentId }: { paymentId: string }) {
  const theme = useTheme();
  const { refreshUser } = useAuth();
  const { data: payment, error } = useApiQuery<Payment>(`/billing/payments/${paymentId}/`, {
    refetchInterval: (data) => (!data || data.status === 'pending' ? POLL_MS : false),
  });
  const paid = payment?.status === 'paid';

  // The account now has a plan; the rest of the app reads it from the user.
  useEffect(() => {
    if (paid) refreshUser().catch(() => {});
  }, [paid, refreshUser]);

  if (error) {
    return (
      <Page maxWidth={640}>
        <ThemedText themeColor="danger">{error.message}</ThemedText>
      </Page>
    );
  }
  if (!payment || payment.status === 'pending') {
    return (
      <Page maxWidth={640}>
        <View style={styles.center}>
          <ActivityIndicator size="large" color={theme.primary} />
          <ThemedText type="subtitle">Sprawdzamy płatność…</ThemedText>
          <ThemedText themeColor="textSecondary" style={styles.text}>
            Zwykle trwa to kilka sekund. Potwierdzenie wyślemy też e-mailem.
          </ThemedText>
        </View>
      </Page>
    );
  }
  if (paid) {
    return (
      <Page maxWidth={640}>
        <View style={[styles.card, { backgroundColor: theme.primaryMuted, borderColor: theme.primary }]}>
          <View style={[styles.icon, { backgroundColor: theme.primary }]}>
            <Icon name="check" size={28} tintColor={theme.onPrimary} />
          </View>
          <ThemedText type="title">Plan {payment.plan_name} jest aktywny</ThemedText>
          <ThemedText themeColor="textSecondary">
            Dziękujemy za płatność.
            {payment.period_end
              ? ` Następna pobierze się sama z zapisanej karty ${formatDate(payment.period_end)}.`
              : ''}
          </ThemedText>
          <Link href="/shops/new" asChild>
            <Button title="Załóż sklep" icon="plus" size="large" />
          </Link>
          <Link href="/billing" asChild>
            <Button title="Plan i płatności" variant="ghost" />
          </Link>
        </View>
      </Page>
    );
  }
  return (
    <Page maxWidth={640}>
      <View style={[styles.card, { backgroundColor: theme.dangerMuted, borderColor: theme.danger }]}>
        <ThemedText type="title">Płatność się nie udała</ThemedText>
        <ThemedText>{payment.error || 'Operator płatności jej nie zrealizował.'} Nie pobraliśmy pieniędzy.</ThemedText>
        <Link href="/billing/checkout" asChild>
          <Button title="Spróbuj ponownie" icon="refresh" size="large" />
        </Link>
      </View>
    </Page>
  );
}

const styles = StyleSheet.create({
  center: {
    alignItems: 'center',
    gap: Spacing.three,
    paddingVertical: Spacing.six,
  },
  text: {
    textAlign: 'center',
  },
  card: {
    gap: Spacing.three,
    padding: Spacing.five,
    borderRadius: Radius.large,
    borderWidth: 1.5,
  },
  icon: {
    width: 52,
    height: 52,
    borderRadius: 26,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
