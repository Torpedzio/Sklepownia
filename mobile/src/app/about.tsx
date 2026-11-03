import { Link } from 'expo-router';
import { Platform, StyleSheet, useWindowDimensions, View } from 'react-native';

import { FaqList } from '@/components/faq-list';
import { FeatureList } from '@/components/feature-list';
import { Page } from '@/components/page';
import { Receipt } from '@/components/receipt';
import { SiteFooter } from '@/components/site-footer';
import { SiteHeader } from '@/components/site-header';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Brand } from '@/constants/brand';
import { Faq, Features, SetupSteps } from '@/constants/content';
import { ReadableWidth, Spacing, WideBreakpoint } from '@/constants/theme';
import { useAuth } from '@/context/auth';

export default function AboutScreen() {
  const { user } = useAuth();
  const { width } = useWindowDimensions();
  const wide = width >= WideBreakpoint;
  const web = Platform.OS === 'web';

  return (
    <Page top={web ? <SiteHeader /> : undefined} bottom={web ? <SiteFooter /> : undefined} contentContainerStyle={styles.page}>
      <View style={styles.intro}>
        <ThemedText type="title">Jak to działa</ThemedText>
        <ThemedText type="lead" themeColor="textSecondary">
          {Brand.name} zakłada sklepy internetowe dla osób, które chcą sprzedawać, a nie konfigurować serwery.
          Wypełniasz krótki formularz w aplikacji, a my stawiamy sklep na WordPressie z WooCommerce:
          gotowy do przyjmowania zamówień, po polsku, z kategoriami dopasowanymi do Twojej branży.
        </ThemedText>
      </View>

      <View style={[styles.split, wide && styles.splitWide]}>
        <View style={[styles.splitText, wide && styles.flex]}>
          <ThemedText type="subtitle">Co dzieje się po kliknięciu „Załóż sklep”</ThemedText>
          <ThemedText themeColor="textSecondary">
            Twój sklep dostaje własną bazę danych i własne środowisko. Instalujemy WordPressa i WooCommerce,
            ustawiamy język, walutę i strefę czasową, włączamy wybrany motyw, tworzymy kategorie i pasek
            z wyszukiwarką oraz filtrami.
          </ThemedText>
          <ThemedText themeColor="textSecondary">
            Na końcu sprawdzamy, czy sklep odpowiada. Każdy krok widzisz w aplikacji na bieżąco. Jeśli któryś
            się nie uda, przycisk „Spróbuj ponownie” ruszy dokładnie od tego miejsca.
          </ThemedText>
        </View>
        <View style={[styles.receipt, wide && styles.receiptWide]}>
          <Receipt
            title="Zakładanie sklepu"
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

      <View style={styles.cta}>
        <ThemedText type="heading">Nie znalazłeś odpowiedzi?</ThemedText>
        <View style={styles.actions}>
          <Link href="/contact" asChild>
            <Button title="Napisz do nas" variant="secondary" icon="mail" />
          </Link>
          {user ? null : (
            <Link href="/sign-up" asChild>
              <Button title="Załóż konto" />
            </Link>
          )}
        </View>
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
  cta: {
    gap: Spacing.three,
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
});
