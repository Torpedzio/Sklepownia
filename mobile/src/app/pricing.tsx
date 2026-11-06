import { Link } from 'expo-router';
import { ActivityIndicator, Platform, StyleSheet, View } from 'react-native';

import { Page } from '@/components/page';
import { PlanCard } from '@/components/plan-card';
import { SiteFooter } from '@/components/site-footer';
import { SiteHeader } from '@/components/site-header';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useApiQuery } from '@/hooks/use-api-query';
import type { Plan } from '@/lib/types';

export default function PricingScreen() {
  const { user } = useAuth();
  const { data: plans, error } = useApiQuery<Plan[]>('/billing/plans/');
  const web = Platform.OS === 'web';

  return (
    <Page top={web ? <SiteHeader /> : undefined} bottom={web ? <SiteFooter /> : undefined}>
      <View style={styles.intro}>
        <ThemedText type="title">Cennik</ThemedText>
        <ThemedText type="lead" themeColor="textSecondary">
          Jedna opłata za sklepy, serwer, aktualizacje i pomoc. Ceny zawierają VAT. Płacisz kartą co miesiąc i anulujesz
          w każdej chwili.
        </ThemedText>
      </View>

      {error ? <ThemedText themeColor="danger">{error.message}</ThemedText> : null}
      {!plans && !error ? <ActivityIndicator style={styles.loader} /> : null}

      <View style={styles.plans}>
        {plans?.map((plan) => (
          <PlanCard key={plan.code} plan={plan}>
            {!user ? (
              <Link href="/sign-up" asChild>
                <Button title="Załóż konto" size="large" />
              </Link>
            ) : !user.is_email_verified ? (
              <Link href="/verify-email" asChild>
                <Button title="Potwierdź e-mail, żeby wybrać plan" size="large" />
              </Link>
            ) : user.plan ? (
              <Link href="/billing" asChild>
                <Button title="Plan i płatności" variant="secondary" size="large" />
              </Link>
            ) : (
              <Link href={{ pathname: '/billing/checkout', params: { plan: plan.code } }} asChild>
                <Button title="Wybierz plan" size="large" />
              </Link>
            )}
          </PlanCard>
        ))}
      </View>

      <ThemedText type="small" themeColor="textSecondary" style={styles.note}>
        Faktury wystawiamy dla firm i osób prywatnych. Płatności obsługuje Tpay: dane karty wpisujesz na stronie
        operatora i nie trafiają do nas.
      </ThemedText>
    </Page>
  );
}

const styles = StyleSheet.create({
  intro: {
    gap: Spacing.two,
    maxWidth: 640,
  },
  loader: {
    marginVertical: Spacing.six,
  },
  plans: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
  note: {
    maxWidth: 640,
  },
});
