import { Link, Stack } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { BillingProfileForm, EMPTY_PROFILE } from '@/components/billing-profile-form';
import { Icon } from '@/components/icon';
import { Page } from '@/components/page';
import { periodLabel } from '@/components/plan-card';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing, type ThemeColor } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api, ApiError } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import { formatDate, formatMoney } from '@/lib/format';
import type { BillingOverview, BillingProfile, Payment, Subscription } from '@/lib/types';

const STATUS_TONE: Record<Subscription['status'], [ThemeColor, ThemeColor]> = {
  active: ['success', 'primaryMuted'],
  past_due: ['warning', 'accentMuted'],
  incomplete: ['textSecondary', 'surfaceMuted'],
  canceled: ['textSecondary', 'surfaceMuted'],
  expired: ['danger', 'dangerMuted'],
};

export default function BillingScreen() {
  const { data, error, refresh } = useApiQuery<BillingOverview>('/billing/');

  if (!data) {
    return (
      <Page>
        {error ? (
          <ThemedText themeColor="danger">{error.message}</ThemedText>
        ) : (
          <ActivityIndicator style={styles.loader} />
        )}
      </Page>
    );
  }
  return (
    <Page maxWidth={760}>
      <Stack.Screen options={{ title: 'Plan i płatności', ...backArrowOptions('/account', 'Wróć do konta') }} />
      <ThemedText type="title">Plan i płatności</ThemedText>
      <PlanSection subscription={data.subscription} onChange={refresh} />
      <ProfileSection profile={data.profile} onSaved={refresh} />
      <History payments={data.payments} />
    </Page>
  );
}

function PlanSection({ subscription, onChange }: { subscription: Subscription | null; onChange: () => Promise<void> }) {
  const theme = useTheme();
  const notify = useNotify();
  const { refreshUser } = useAuth();
  const [busy, setBusy] = useState(false);
  const running = subscription && ['active', 'past_due'].includes(subscription.status);

  if (!subscription || !running) {
    return (
      <Card>
        <ThemedText type="heading">
          {subscription && subscription.status !== 'incomplete'
            ? `Plan ${subscription.plan.name} się zakończył`
            : 'Nie masz jeszcze planu'}
        </ThemedText>
        <ThemedText themeColor="textSecondary">Z planem założysz sklepy. Sklepy testowe działają bez planu.</ThemedText>
        <Link href="/billing/checkout" asChild>
          <Button title="Wybierz plan" icon="card" style={styles.start} />
        </Link>
      </Card>
    );
  }

  const { plan } = subscription;
  const [color, background] = STATUS_TONE[subscription.status];

  async function change(action: 'cancel' | 'resume') {
    if (
      action === 'cancel' &&
      !(await confirm(
        'Anulować plan?',
        `Plan działa do ${formatDate(subscription!.current_period_end!)}. Potem nie odnowimy go i nie założysz nowych sklepów.`,
        'Anuluj plan',
      ))
    ) {
      return;
    }
    setBusy(true);
    try {
      await api(`/billing/subscription/${action}/`, { method: 'POST' });
      notify.success(action === 'cancel' ? 'Plan nie będzie odnawiany.' : 'Plan będzie odnawiany jak dotąd.');
      await Promise.all([onChange(), refreshUser()]);
    } catch (e) {
      notify.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <View style={styles.planHead}>
        <View style={styles.flex}>
          <ThemedText type="heading">Plan {plan.name}</ThemedText>
          <ThemedText themeColor="textSecondary">
            {formatMoney(plan.price, plan.currency)} / {periodLabel(plan.interval_months)}, do {plan.max_shops} sklepów
          </ThemedText>
        </View>
        <View style={[styles.badge, { backgroundColor: theme[background] }]}>
          <ThemedText type="smallBold" themeColor={color}>
            {subscription.cancel_at_period_end ? 'Anulowany' : subscription.status_display}
          </ThemedText>
        </View>
      </View>

      {subscription.status === 'past_due' ? (
        <View style={[styles.notice, { backgroundColor: theme.accentMuted }]}>
          <Icon name="warning" size={18} tintColor={theme.warning} />
          <ThemedText type="small" style={styles.flex}>
            Nie udało się pobrać opłaty z karty.
            {subscription.next_attempt_at
              ? ` Spróbujemy ponownie ${formatDate(subscription.next_attempt_at)}.`
              : ''}{' '}
            Sprawdź, czy karta jest ważna i ma środki. Do tego czasu nie założysz nowych sklepów.
          </ThemedText>
        </View>
      ) : null}

      {subscription.current_period_end ? (
        <ThemedText>
          {subscription.cancel_at_period_end
            ? `Plan działa do ${formatDate(subscription.current_period_end)}. Nie odnowimy go.`
            : `Następna płatność ${formatDate(subscription.current_period_end)}: ${formatMoney(
                Math.max(Number(plan.price) - Number(subscription.credit), 0),
                plan.currency,
              )}.`}
        </ThemedText>
      ) : null}
      {subscription.card ? (
        <View style={styles.cardRow}>
          <Icon name="card" size={18} color="textSecondary" />
          <ThemedText themeColor="textSecondary">
            {subscription.card.brand} •••• {subscription.card.tail}
          </ThemedText>
        </View>
      ) : null}

      {Number(subscription.credit) > 0 ? (
        <ThemedText themeColor="textSecondary">
          Saldo nadpłaty: {formatMoney(subscription.credit, plan.currency)}. Odliczymy je od kolejnych płatności.
        </ThemedText>
      ) : null}

      <View style={styles.buttons}>
        {subscription.status === 'active' ? (
          <Link href="/billing/change" asChild>
            <Button title="Zmień plan" icon="filter" />
          </Link>
        ) : null}
        {subscription.cancel_at_period_end ? (
          <Button title="Wznów plan" variant="secondary" loading={busy} onPress={() => change('resume')} />
        ) : (
          <Button title="Anuluj plan" variant="danger" loading={busy} onPress={() => change('cancel')} />
        )}
      </View>
    </Card>
  );
}

function ProfileSection({ profile, onSaved }: { profile: BillingProfile | null; onSaved: () => Promise<void> }) {
  const notify = useNotify();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<BillingProfile>(profile ?? EMPTY_PROFILE);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await api('/billing/profile/', { method: 'PUT', body: draft });
      setErrors({});
      setEditing(false);
      notify.success('Zapisano dane do faktury.');
      await onSaved();
    } catch (e) {
      if (e instanceof ApiError) setErrors(e.fieldErrors);
      notify.error(e instanceof ApiError && e.status === 400 ? 'Popraw zaznaczone pola.' : (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <ThemedText type="heading">Dane do faktury</ThemedText>
      {editing ? (
        <>
          <BillingProfileForm value={draft} onChange={setDraft} errors={errors} />
          <View style={styles.buttons}>
            <Button title="Zapisz" icon="check" loading={saving} onPress={save} />
            <Button title="Anuluj" variant="ghost" onPress={() => setEditing(false)} disabled={saving} />
          </View>
        </>
      ) : (
        <>
          {profile ? (
            <View style={styles.profile}>
              <ThemedText type="smallBold">
                {profile.kind === 'company' ? profile.company_name : profile.full_name}
              </ThemedText>
              {profile.kind === 'company' ? (
                <ThemedText type="small" themeColor="textSecondary">
                  NIP {profile.tax_id}, {profile.full_name}
                </ThemedText>
              ) : null}
              <ThemedText type="small" themeColor="textSecondary">
                {profile.street}, {profile.postal_code} {profile.city}
              </ThemedText>
            </View>
          ) : (
            <ThemedText themeColor="textSecondary">Podasz je przy wyborze planu.</ThemedText>
          )}
          {profile ? (
            <Button
              title="Zmień dane"
              variant="secondary"
              onPress={() => {
                setDraft(profile);
                setEditing(true);
              }}
              style={styles.start}
            />
          ) : null}
        </>
      )}
    </Card>
  );
}

function History({ payments }: { payments: Payment[] }) {
  const theme = useTheme();
  if (!payments.length) return null;
  return (
    <Card>
      <ThemedText type="heading">Historia płatności</ThemedText>
      {payments.map((payment, index) => (
        <View
          key={payment.id}
          style={[styles.payment, index > 0 && { borderTopColor: theme.border, borderTopWidth: 1 }]}>
          <View style={styles.flex}>
            <ThemedText type="smallBold">
              {payment.kind_display}, plan {payment.plan_name}
            </ThemedText>
            <ThemedText type="small" themeColor="textSecondary">
              {formatDate(payment.paid_at ?? payment.created_at)}
              {payment.gateway_title ? `, ${payment.gateway_title}` : ''}
              {Number(payment.credit_used) > 0 ? `, z salda ${formatMoney(payment.credit_used, payment.currency)}` : ''}
            </ThemedText>
            {payment.status === 'failed' && payment.error ? (
              <ThemedText type="small" themeColor="danger">
                {payment.error}
              </ThemedText>
            ) : null}
          </View>
          <View style={styles.amount}>
            <ThemedText type="smallBold">{formatMoney(payment.amount, payment.currency)}</ThemedText>
            <ThemedText type="small" themeColor={payment.status === 'failed' ? 'danger' : 'textSecondary'}>
              {payment.status_display}
            </ThemedText>
          </View>
        </View>
      ))}
    </Card>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  const theme = useTheme();
  return <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>{children}</View>;
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  loader: {
    marginVertical: Spacing.six,
  },
  start: {
    alignSelf: 'flex-start',
  },
  card: {
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  planHead: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: Spacing.three,
  },
  badge: {
    paddingHorizontal: Spacing.two + Spacing.one,
    paddingVertical: Spacing.half,
    borderRadius: Radius.pill,
  },
  notice: {
    flexDirection: 'row',
    gap: Spacing.two,
    padding: Spacing.three,
    borderRadius: Radius.medium,
  },
  cardRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  buttons: {
    flexDirection: 'row',
    gap: Spacing.two,
  },
  profile: {
    gap: Spacing.half,
  },
  payment: {
    flexDirection: 'row',
    gap: Spacing.three,
    paddingTop: Spacing.two,
  },
  amount: {
    alignItems: 'flex-end',
  },
});
