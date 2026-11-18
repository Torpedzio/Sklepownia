import { ActivityIndicator, Platform, StyleSheet, View } from 'react-native';

import { FaqList } from '@/components/faq-list';
import { Page } from '@/components/page';
import { PlanAction } from '@/components/plan-action';
import { PlanCard } from '@/components/plan-card';
import { SiteFooter } from '@/components/site-footer';
import { SiteHeader } from '@/components/site-header';
import { ThemedText } from '@/components/themed-text';
import { PricingFaq } from '@/constants/content';
import { Spacing } from '@/constants/theme';
import { usePlans } from '@/hooks/use-plans';
import { loadPlans } from '@/lib/plans';

// On the web the server puts the plans in the page (see usePlans).
export const loader = loadPlans;

export default function PricingScreen() {
  const { plans, error } = usePlans();
  const web = Platform.OS === 'web';

  return (
    <Page top={web ? <SiteHeader /> : undefined} bottom={web ? <SiteFooter /> : undefined}>
      <View style={styles.intro}>
        <ThemedText type="title">Cennik</ThemedText>
        <ThemedText type="lead" themeColor="textSecondary">
          Jedna opłata za sklepy, serwer, aktualizacje i pomoc. Ceny zawierają VAT. Płacisz kartą co miesiąc, a plan
          zmieniasz albo anulujesz w każdej chwili.
        </ThemedText>
      </View>

      {error ? <ThemedText themeColor="danger">{error.message}</ThemedText> : null}
      {!plans && !error ? <ActivityIndicator style={styles.loader} /> : null}

      <View style={styles.plans}>
        {plans?.map((plan) => (
          <PlanCard key={plan.code} plan={plan}>
            <PlanAction plan={plan} />
          </PlanCard>
        ))}
      </View>

      <ThemedText type="small" themeColor="textSecondary" style={styles.note}>
        Faktury wystawiamy dla firm i osób prywatnych. Płatności obsługuje Tpay: dane karty wpisujesz na stronie
        operatora i nie trafiają do nas.
      </ThemedText>

      <View style={styles.faq}>
        <ThemedText type="subtitle">Pytania o plany i płatności</ThemedText>
        <FaqList items={PricingFaq} />
      </View>
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
  faq: {
    gap: Spacing.three,
    marginTop: Spacing.four,
  },
});
