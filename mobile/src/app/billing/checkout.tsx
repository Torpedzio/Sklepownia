import { Link, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { BillingProfileForm, EMPTY_PROFILE } from '@/components/billing-profile-form';
import { Page } from '@/components/page';
import { periodLabel, PlanCard } from '@/components/plan-card';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { SwitchRow } from '@/components/ui/switch-row';
import { Radius, Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api, ApiError } from '@/lib/api';
import { formatMoney } from '@/lib/format';
import { goToPayment, paymentReturnUrl } from '@/lib/payment';
import type { BillingOverview, BillingProfile, Checkout, Plan } from '@/lib/types';

const ACTIVE = ['active', 'past_due'];

export default function CheckoutScreen() {
  const { plan: planCode } = useLocalSearchParams<{ plan?: string }>();
  const { data: plans, error: plansError } = useApiQuery<Plan[]>('/billing/plans/');
  const { data: overview, error } = useApiQuery<BillingOverview>('/billing/');
  const problem = plansError ?? error;

  if (!plans || !overview) {
    return (
      <Page>
        {problem ? (
          <ThemedText themeColor="danger">{problem.message}</ThemedText>
        ) : (
          <ActivityIndicator style={styles.loader} />
        )}
      </Page>
    );
  }
  const subscription = overview.subscription;
  if (subscription && ACTIVE.includes(subscription.status)) {
    return (
      <Page maxWidth={760}>
        <ThemedText type="title">Masz już plan {subscription.plan.name}</ThemedText>
        <ThemedText themeColor="textSecondary">Zmianę planu i kartę zobaczysz w ustawieniach płatności.</ThemedText>
        <Link href="/billing" asChild>
          <Button title="Plan i płatności" style={styles.start} />
        </Link>
      </Page>
    );
  }
  return (
    <CheckoutForm
      plans={plans}
      initialPlan={
        (plans.find((plan) => plan.code === planCode) ?? plans.find((plan) => plan.is_featured) ?? plans[0])?.code
      }
      initialProfile={overview.profile ?? EMPTY_PROFILE}
    />
  );
}

type CheckoutFormProps = { plans: Plan[]; initialPlan: string | undefined; initialProfile: BillingProfile };

function CheckoutForm({ plans, initialPlan, initialProfile }: CheckoutFormProps) {
  const theme = useTheme();
  const notify = useNotify();
  const [planCode, setPlanCode] = useState(initialPlan);
  const [profile, setProfile] = useState(initialProfile);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [startNow, setStartNow] = useState(false);
  const [paying, setPaying] = useState(false);
  const plan = plans.find((item) => item.code === planCode);
  const person = profile.kind === 'individual';

  async function pay() {
    if (!plan) return;
    setPaying(true);
    setErrors({});
    try {
      await api('/billing/profile/', { method: 'PUT', body: profile });
    } catch (e) {
      if (e instanceof ApiError) setErrors(e.fieldErrors);
      notify.error(
        e instanceof ApiError && e.status === 400 ? 'Popraw zaznaczone dane do faktury.' : (e as Error).message,
      );
      setPaying(false);
      return;
    }
    try {
      const checkout = await api<Checkout>('/billing/checkout/', {
        method: 'POST',
        body: {
          plan: plan.code,
          return_url: paymentReturnUrl(),
          accept_terms: acceptTerms,
          immediate_start_consent: person && startNow,
        },
      });
      await goToPayment(checkout);
    } catch (e) {
      const fieldErrors = e instanceof ApiError ? e.fieldErrors : {};
      notify.error(fieldErrors.accept_terms ?? fieldErrors.return_url ?? (e as Error).message);
      setPaying(false);
    }
  }

  return (
    <Page maxWidth={760}>
      <Stack.Screen options={{ title: 'Wybierz plan', ...backArrowOptions('/billing', 'Wróć') }} />
      <View style={styles.intro}>
        <ThemedText type="title">Wybierz plan</ThemedText>
        <ThemedText themeColor="textSecondary">
          Z planem założysz sklepy. Płacisz kartą, a kolejne miesiące opłacamy z zapisanej karty.
        </ThemedText>
      </View>

      <Section title="Plan">
        <View style={styles.plans} accessibilityRole="radiogroup">
          {plans.map((item) => (
            <PlanCard
              key={item.code}
              plan={item}
              selected={item.code === planCode}
              onSelect={() => setPlanCode(item.code)}
            />
          ))}
        </View>
      </Section>

      <Section title="Dane do faktury">
        <BillingProfileForm value={profile} onChange={setProfile} errors={errors} />
      </Section>

      <Section title="Płatność">
        {plan ? (
          <View style={[styles.summary, { backgroundColor: theme.surfaceMuted }]}>
            <View style={styles.summaryRow}>
              <ThemedText>Plan {plan.name}</ThemedText>
              <ThemedText type="smallBold">{formatMoney(plan.price, plan.currency)}</ThemedText>
            </View>
            <ThemedText type="small" themeColor="textSecondary">
              Cena brutto, zawiera {Number(plan.vat_rate)}% VAT. Potem co {periodLabel(plan.interval_months)} z
              zapisanej karty. Plan anulujesz w każdej chwili w Koncie, w zakładce Plan i płatności.
            </ThemedText>
          </View>
        ) : null}
        <SwitchRow
          label="Akceptuję regulamin usługi"
          value={acceptTerms}
          onChange={setAcceptTerms}
          error={errors.accept_terms}
        />
        {person ? (
          <SwitchRow
            label="Chcę, żeby usługa zaczęła działać od razu"
            description="Prosisz o rozpoczęcie usługi przed upływem 14 dni na odstąpienie od umowy."
            value={startNow}
            onChange={setStartNow}
          />
        ) : null}
        <Button
          title={plan ? `Zapłać kartą ${formatMoney(plan.price, plan.currency)}` : 'Zapłać kartą'}
          icon="card"
          size="large"
          loading={paying}
          disabled={!plan || !acceptTerms || (person && !startNow)}
          onPress={pay}
        />
        <ThemedText type="small" themeColor="textSecondary">
          Płatność obsługuje Tpay. Dane karty wpisujesz na stronie operatora i nie trafiają do nas.
        </ThemedText>
      </Section>
    </Page>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const theme = useTheme();
  return (
    <View style={[styles.section, { borderTopColor: theme.border }]}>
      <ThemedText type="subtitle">{title}</ThemedText>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  loader: {
    marginVertical: Spacing.six,
  },
  start: {
    alignSelf: 'flex-start',
  },
  intro: {
    gap: Spacing.two,
  },
  section: {
    gap: Spacing.three,
    paddingTop: Spacing.four,
    borderTopWidth: 1,
  },
  plans: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
  summary: {
    gap: Spacing.one,
    padding: Spacing.three,
    borderRadius: Radius.medium,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: Spacing.three,
  },
});
