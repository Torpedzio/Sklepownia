import { Link } from 'expo-router';
import { Platform, StyleSheet, View } from 'react-native';

import { CtaBand } from '@/components/cta-band';
import { FaqList } from '@/components/faq-list';
import { FeatureList } from '@/components/feature-list';
import { Page } from '@/components/page';
import { Receipt } from '@/components/receipt';
import { SiteFooter } from '@/components/site-footer';
import { SiteHeader } from '@/components/site-header';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Brand } from '@/constants/brand';
import { Faq, Features, PricingFaq, SetupSteps } from '@/constants/content';
import { ReadableWidth, Spacing, WideBreakpoint } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useWindowDimensions } from '@/hooks/use-window-dimensions';

export default function AboutScreen() {
  const { user } = useAuth();
  const { width } = useWindowDimensions();
  const wide = width >= WideBreakpoint;
  const web = Platform.OS === 'web';

  return (
    <Page
      top={web ? <SiteHeader /> : undefined}
      bottom={
        <>
          <CtaBand title="Nie znalazłeś odpowiedzi?">
            <Link href="/contact" asChild>
              <Button title="Napisz do nas" variant={user ? 'accent' : 'secondary'} size="large" icon="mail" />
            </Link>
            {user ? null : (
              <Link href="/sign-up" asChild>
                <Button title="Załóż konto" variant="accent" size="large" />
              </Link>
            )}
          </CtaBand>
          {web ? <SiteFooter /> : null}
        </>
      }
      contentContainerStyle={styles.page}>
      <View style={styles.intro}>
        <ThemedText type="title">Jak to działa</ThemedText>
        <ThemedText type="lead" themeColor="textSecondary">
          {Brand.name} zakłada sklepy internetowe dla osób, które chcą sprzedawać, a nie konfigurować serwery.
          Wypełniasz krótki formularz w aplikacji, a my stawiamy sklep na wybranym systemie: WooCommerce, PrestaShop
          albo Magento. Sklep jest gotowy do przyjmowania zamówień, w wybranym języku i walucie, z kategoriami
          dopasowanymi do Twojej branży. Płacisz
          miesięczny abonament za plan, a serwer, aktualizacje i utrzymanie sklepu są po naszej stronie.
        </ThemedText>
      </View>

      <View style={[styles.split, wide && styles.splitWide]}>
        <View style={[styles.splitText, wide && styles.flex]}>
          <ThemedText type="subtitle">Co dzieje się po kliknięciu „Załóż sklep”</ThemedText>
          <ThemedText themeColor="textSecondary">
            Twój sklep dostaje własną bazę danych i własne środowisko. Instalujemy wybrany system, ustawiamy język,
            walutę i strefę czasową, włączamy motyw, tworzymy kategorie, menu, wyszukiwarkę i filtry.
          </ThemedText>
          <ThemedText themeColor="textSecondary">
            Na końcu sprawdzamy, czy sklep odpowiada. Każdy krok widzisz w aplikacji na bieżąco. Jeśli któryś się nie
            uda, przycisk „Spróbuj ponownie” ruszy dokładnie od tego miejsca.
          </ThemedText>
        </View>
        <View style={[styles.receipt, wide && styles.receiptWide]}>
          <Receipt
            title="Zakładanie sklepu WooCommerce"
            rows={SetupSteps.map((step) => ({ label: step.label }))}
            total={{ label: 'Razem', value: 'ok. 2 min' }}
          />
        </View>
      </View>

      <View style={styles.block}>
        <ThemedText type="subtitle">Co jest w środku</ThemedText>
        <FeatureList features={Features} />
      </View>

      <View style={styles.block}>
        <ThemedText type="subtitle">Pytania i odpowiedzi</ThemedText>
        <FaqList items={Faq} />
      </View>

      <View style={styles.block}>
        <ThemedText type="subtitle">Plany i płatności</ThemedText>
        <FaqList items={PricingFaq} />
        <Link href="/pricing">
          <ThemedText type="link">Zobacz cennik</ThemedText>
        </Link>
      </View>
    </Page>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  page: {
    gap: Spacing.six,
  },
  intro: {
    gap: Spacing.three,
    maxWidth: ReadableWidth + 80,
  },
  split: {
    gap: Spacing.five,
  },
  splitWide: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  splitText: {
    gap: Spacing.three,
    maxWidth: ReadableWidth,
  },
  receipt: {
    width: '100%',
    maxWidth: 380,
  },
  receiptWide: {
    width: 360,
  },
  block: {
    gap: Spacing.three,
  },
});
