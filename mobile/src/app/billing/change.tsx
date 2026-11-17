import { router, Stack } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { Icon } from '@/components/icon';
import { Page } from '@/components/page';
import { periodLabel, PlanCard, planShopsLabel } from '@/components/plan-card';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api, ApiError } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import { formatDate, formatMoney } from '@/lib/format';
import { goToPayment, paymentReturnUrl } from '@/lib/payment';
import { toggleKept } from '@/lib/plan-change';
import type { BillingOverview, Plan, PlanChangePreview, PlanChangeResult, Subscription } from '@/lib/types';

export default function ChangePlanScreen() {
  const { data: plans, error: plansError } = useApiQuery<Plan[]>('/billing/plans/');
  const { data: overview, error } = useApiQuery<BillingOverview>('/billing/');
  const problem = plansError ?? error;
  const subscription = overview?.subscription;

  return (
    <Page maxWidth={1040}>
      <Stack.Screen options={{ title: 'Zmień plan', ...backArrowOptions('/billing', 'Wróć do planu i płatności') }} />
      <View style={styles.intro}>
        <ThemedText type="title">Zmień plan</ThemedText>
        <ThemedText themeColor="textSecondary">
          Nowy plan działa od razu, a data płatności się nie zmienia. Za wyższy plan dopłacasz tylko za dni, które
          zostały w opłaconym okresie. Przy niższym niewykorzystana kwota pomniejszy kolejne płatności.
        </ThemedText>
      </View>
      {problem ? <ThemedText themeColor="danger">{problem.message}</ThemedText> : null}
      {!problem && (!plans || !overview) ? <ActivityIndicator style={styles.loader} /> : null}
      {plans && subscription ? <ChangeForm plans={plans} subscription={subscription} /> : null}
      {plans && overview && !subscription ? (
        <ThemedText themeColor="textSecondary">
          Nie masz jeszcze planu. Wybierz go w zakładce Plan i płatności.
        </ThemedText>
      ) : null}
    </Page>
  );
}

function ChangeForm({ plans, subscription }: { plans: Plan[]; subscription: Subscription }) {
  const notify = useNotify();
  const { refreshUser } = useAuth();
  const [chosen, setChosen] = useState<string>();
  const [keep, setKeep] = useState<number[]>();
  const [preview, setPreview] = useState<PlanChangePreview>();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // The preview is computed by the server, so the amounts shown are the ones charged. Which shops stay doesn't
  // change the amounts, so picking them happens here and the server checks the choice when the plan changes.
  useEffect(() => {
    if (!chosen) return;
    let current = true;
    api<PlanChangePreview>('/billing/subscription/change-preview/', { method: 'POST', body: { plan: chosen } })
      .then((result) => current && setPreview(result))
      .catch((e: Error) => current && notify.error(e.message))
      .finally(() => current && setLoading(false));
    return () => {
      current = false;
    };
  }, [chosen, notify]);

  const kept = keep ?? preview?.keep.map((shop) => shop.id) ?? [];
  const suspended = preview ? [...preview.keep, ...preview.suspend].filter((shop) => !kept.includes(shop.id)) : [];

  function choose(code: string) {
    if (code === subscription.plan.code) return;
    setLoading(true);
    setPreview(undefined);
    setKeep(undefined);
    setChosen(code);
  }

  function toggleShop(id: number) {
    if (!preview) return;
    const shops = [...preview.keep, ...preview.suspend];
    const result = toggleKept(shops, kept, id, preview.plan);
    if ('error' in result) notify.error(result.error);
    else setKeep(result.keep);
  }

  async function submit() {
    if (!preview || !chosen) return;
    if (
      suspended.length &&
      !(await confirm(
        'Zawiesić sklepy?',
        `${suspended.map((shop) => shop.name).join(', ')}: klienci przestaną je widzieć. Nic z nich nie zniknie, a przywrócisz je po zmianie planu.`,
        'Zmień plan',
      ))
    ) {
      return;
    }
    setSaving(true);
    try {
      const result = await api<PlanChangeResult>('/billing/subscription/change/', {
        method: 'POST',
        body: { plan: chosen, return_url: paymentReturnUrl(), ...(keep ? { keep_shops: keep } : {}) },
      });
      if (result.payment && result.redirect_url) {
        await goToPayment({ payment: result.payment, redirect_url: result.redirect_url });
        return;
      }
      notify.success(`Masz teraz plan ${result.change.plan.name}.`);
      await refreshUser();
      router.replace('/billing');
    } catch (e) {
      notify.error(e instanceof ApiError ? e.message : (e as Error).message);
      setSaving(false);
    }
  }

  return (
    <>
      <View style={styles.plans} accessibilityRole="radiogroup">
        {plans.map((plan) => {
          const current = plan.code === subscription.plan.code;
          return (
            <PlanCard
              key={plan.code}
              plan={plan}
              selected={plan.code === chosen}
              onSelect={current ? undefined : () => choose(plan.code)}>
              {current ? (
                <ThemedText type="smallBold" themeColor="primary">
                  Twój plan
                </ThemedText>
              ) : null}
            </PlanCard>
          );
        })}
      </View>

      {loading ? <ActivityIndicator style={styles.loader} /> : null}
      {preview && !loading ? (
        <Summary
          preview={preview}
          subscription={subscription}
          keep={kept}
          onToggleShop={toggleShop}
          saving={saving}
          onSubmit={submit}
        />
      ) : null}
    </>
  );
}

type SummaryProps = {
  preview: PlanChangePreview;
  subscription: Subscription;
  keep: number[];
  onToggleShop: (id: number) => void;
  saving: boolean;
  onSubmit: () => void;
};

function Summary({ preview, subscription, keep, onToggleShop, saving, onSubmit }: SummaryProps) {
  const theme = useTheme();
  const { plan } = preview;
  const money = (amount: string | number) => formatMoney(amount, plan.currency);
  const periodEnd = subscription.current_period_end ? formatDate(subscription.current_period_end) : null;
  const nextPayment = Math.max(Number(plan.price) - Number(preview.credit_after), 0);
  const counted = [...preview.keep, ...preview.suspend];
  // Shops are suspended only when they don't fit the new plan; then the owner picks which stay.
  const choosing = preview.suspend.length > 0;
  // A shop being set up can't be suspended; the owner keeps it, or waits until it is ready.
  const settingUp = counted.find(
    (shop) => !keep.includes(shop.id) && (shop.status === 'pending' || shop.status === 'provisioning'),
  );

  if (preview.blocked && !choosing) {
    return (
      <View style={[styles.card, { backgroundColor: theme.accentMuted, borderColor: theme.accent }]}>
        <ThemedText type="heading">Tej zmiany nie da się teraz zrobić</ThemedText>
        <ThemedText>{preview.blocked}</ThemedText>
      </View>
    );
  }

  return (
    <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <ThemedText type="heading">
        {subscription.plan.name} → {plan.name}
      </ThemedText>

      {preview.direction === 'upgrade' ? (
        <ThemedText>
          {Number(preview.amount_due) > 0
            ? `Dopłacisz teraz ${money(preview.amount_due)} za dni do ${periodEnd}.`
            : preview.waived
              ? `Dopłata wyniosłaby ${money(preview.surcharge)}, czyli mniej niż 5 zł, więc zmieniamy plan bez dopłaty.`
              : 'Dopłatę pokryje saldo nadpłaty.'}
          {Number(preview.credit_used) > 0 ? ` Z salda odliczymy ${money(preview.credit_used)}.` : ''}
        </ThemedText>
      ) : (
        <ThemedText>
          Niewykorzystane {money(preview.credit_added)} trafi na saldo i pomniejszy kolejne płatności.
        </ThemedText>
      )}
      {periodEnd ? (
        <ThemedText themeColor="textSecondary">
          Następna płatność {periodEnd}: {money(nextPayment)}, potem {money(plan.price)} co{' '}
          {periodLabel(plan.interval_months)}.
        </ThemedText>
      ) : null}

      {choosing ? (
        <View style={styles.shops}>
          <ThemedText type="smallBold">
            Plan {plan.name} to {planShopsLabel(plan)}. Wybierz, które sklepy zostają aktywne:
          </ThemedText>
          {counted.map((shop) => {
            const kept = keep.includes(shop.id);
            return (
              <Pressable
                key={shop.id}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: kept }}
                onPress={() => onToggleShop(shop.id)}
                style={[styles.shopRow, { borderColor: kept ? theme.primary : theme.border }]}>
                <Icon name={kept ? 'check' : 'pause'} size={18} color={kept ? 'primary' : 'textSecondary'} />
                <View style={styles.flex}>
                  <ThemedText>{shop.name}</ThemedText>
                  <ThemedText type="small" themeColor="textSecondary">
                    {shop.platform_display}
                  </ThemedText>
                </View>
                <ThemedText type="small" themeColor={kept ? 'primary' : 'textSecondary'}>
                  {kept ? 'Zostaje' : 'Zostanie zawieszony'}
                </ThemedText>
              </Pressable>
            );
          })}
          <ThemedText type="small" themeColor="textSecondary">
            Zawieszonych sklepów klienci nie zobaczą, ale nic z nich nie zniknie. Przywrócisz je po zmianie planu albo
            usunięciu innego sklepu.
          </ThemedText>
        </View>
      ) : null}
      {preview.resume.length ? (
        <ThemedText>Wrócą zawieszone sklepy: {preview.resume.map((shop) => shop.name).join(', ')}.</ThemedText>
      ) : null}

      {settingUp ? (
        <ThemedText themeColor="danger">
          Sklep {settingUp.name} jest jeszcze zakładany. Zostaw go aktywnym albo poczekaj, aż będzie gotowy.
        </ThemedText>
      ) : null}

      <Button
        title={Number(preview.amount_due) > 0 ? `Dopłać ${money(preview.amount_due)} i zmień plan` : 'Zmień plan'}
        icon={Number(preview.amount_due) > 0 ? 'card' : 'check'}
        size="large"
        loading={saving}
        disabled={!!settingUp}
        onPress={onSubmit}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  loader: {
    marginVertical: Spacing.four,
  },
  intro: {
    gap: Spacing.two,
  },
  plans: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
  card: {
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1.5,
  },
  shops: {
    gap: Spacing.two,
  },
  shopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
    padding: Spacing.three,
    borderRadius: Radius.medium,
    borderWidth: 1.5,
  },
});
