import { Link } from 'expo-router';
import { StyleSheet, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { CtaBand } from '@/components/cta-band';
import { FaqList } from '@/components/faq-list';
import { FeatureSlides } from '@/components/feature-slides';
import { NewShopButton, paidShopCount } from '@/components/new-shop-button';
import { Page } from '@/components/page';
import { Receipt } from '@/components/receipt';
import { SiteFooter } from '@/components/site-footer';
import { SiteHeader } from '@/components/site-header';
import { ThemeShowcase } from '@/components/theme-showcase';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Faq, Features, SetupSteps } from '@/constants/content';
import { useAuth } from '@/context/auth';
import { Spacing, WideBreakpoint } from '@/constants/theme';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import type { Shop } from '@/lib/types';

const HOME_SLIDES = Features.filter((feature) => feature.homeSlide !== false);

const STEPS = [
  { title: 'Załóż konto', text: 'Wystarczy e-mail i hasło. Potwierdzasz adres kodem z wiadomości.' },
  { title: 'Opisz swój sklep', text: 'Nazwa, adres, branża, motyw i liczba kategorii. Zajmuje to minutę.' },
  { title: 'Otwórz sklep', text: 'Po niecałych dwóch minutach sklep działa, a Ty dostajesz dostęp do panelu.' },
];

export default function HomeScreen() {
  const { user } = useAuth();
  const { data: shops } = useApiQuery<Shop[]>('/shops/', { enabled: !!user });
  const theme = useTheme();
  const { width } = useWindowDimensions();
  const wide = width >= WideBreakpoint;

  return (
    <SafeAreaView style={[styles.flex, { backgroundColor: theme.background }]} edges={['top']}>
      <Page
        top={<SiteHeader />}
        bottom={
          <>
            <ClosingBand shopCount={paidShopCount(shops)} />
            <SiteFooter />
          </>
        }
        contentContainerStyle={styles.page}>
        <View style={[styles.hero, wide && styles.heroWide]}>
          <View style={[styles.heroText, wide && styles.flex]}>
            <ThemedText type="display" style={!wide && styles.displayCompact}>
              Twój sklep internetowy, otwarty w dwie minuty.
            </ThemedText>
            <ThemedText type="lead" themeColor="textSecondary" style={styles.lead}>
              Podajesz nazwę, branżę i wygląd. My stawiamy sklep WooCommerce z kategoriami, wyszukiwarką i panelem
              administracyjnym. Ty dodajesz produkty.
            </ThemedText>
            <View style={styles.actions}>
              {user ? (
                <>
                  <Link href="/shops" asChild>
                    <Button title="Moje sklepy" size="large" icon="store" />
                  </Link>
                  <NewShopButton
                    title="Załóż nowy sklep"
                    variant="secondary"
                    size="large"
                    icon="plus"
                    shopCount={paidShopCount(shops)}
                  />
                </>
              ) : (
                <>
                  <Link href="/sign-up" asChild>
                    <Button title="Załóż konto" size="large" />
                  </Link>
                  <Link href="/about" asChild>
                    <Button title="Zobacz, jak to działa" variant="secondary" size="large" />
                  </Link>
                </>
              )}
            </View>
          </View>
          <View style={[styles.heroReceipt, wide && styles.heroReceiptWide]}>
            <Receipt
              animated
              title="Pracownia Ceramiki"
              subtitle="pracownia-ceramiki.sklepownia.pl"
              rows={SetupSteps.map((step) => ({ label: step.label, value: step.time }))}
              total={{ label: 'Czas zakładania', value: '1:45' }}
              stamp={{ text: 'Otwarte', tone: 'success' }}
            />
          </View>
        </View>

        <FeatureSlides features={HOME_SLIDES} title="Co dostajesz w każdym sklepie" />

        <Section title="Trzy kroki do otwarcia">
          <View style={[styles.steps, wide && styles.stepsWide]}>
            {STEPS.map((step, index) => (
              <View key={step.title} style={styles.step}>
                <ThemedText type="title" themeColor="primary">
                  {index + 1}
                </ThemedText>
                <ThemedText type="heading">{step.title}</ThemedText>
                <ThemedText themeColor="textSecondary">{step.text}</ThemedText>
              </View>
            ))}
          </View>
        </Section>

        <ThemeShowcase
          title="Wybierz wygląd"
          text="Każdy motyw ma lewy pasek z wyszukiwarką, kategoriami i filtrem ceny."
        />

        <Section title="Częste pytania">
          <FaqList items={Faq.slice(0, 4)} />
          <Link href="/about">
            <ThemedText type="link">Wszystkie pytania i odpowiedzi</ThemedText>
          </Link>
        </Section>
      </Page>
    </SafeAreaView>
  );
}

function Section({ title, text, children }: { title: string; text?: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHead}>
        <ThemedText type="title">{title}</ThemedText>
        {text ? (
          <ThemedText type="lead" themeColor="textSecondary">
            {text}
          </ThemedText>
        ) : null}
      </View>
      {children}
    </View>
  );
}

function ClosingBand({ shopCount }: { shopCount: number | undefined }) {
  const { user } = useAuth();
  return (
    <CtaBand title="Zacznij od nazwy sklepu. Resztą zajmiemy się my.">
      {user ? (
        <NewShopButton
          title="Załóż nowy sklep"
          variant="accent"
          size="large"
          shopCount={shopCount}
          tooltipSide="above"
        />
      ) : (
        <Link href="/sign-up" asChild>
          <Button title="Załóż konto" variant="accent" size="large" />
        </Link>
      )}
    </CtaBand>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  page: {
    gap: Spacing.six + Spacing.four,
    paddingTop: Spacing.five,
    paddingBottom: Spacing.six + Spacing.four,
  },
  hero: {
    gap: Spacing.five,
  },
  heroWide: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.six,
  },
  heroText: {
    zIndex: 1,
    gap: Spacing.four,
  },
  displayCompact: {
    fontSize: 40,
    lineHeight: 44,
  },
  lead: {
    maxWidth: 560,
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
  heroReceipt: {
    width: '100%',
    maxWidth: 400,
    alignSelf: 'center',
  },
  heroReceiptWide: {
    width: 380,
    transform: [{ rotate: '1.5deg' }],
  },
  section: {
    gap: Spacing.four,
  },
  sectionHead: {
    gap: Spacing.two,
    maxWidth: 640,
  },
  steps: {
    gap: Spacing.four,
  },
  stepsWide: {
    flexDirection: 'row',
  },
  step: {
    flex: 1,
    gap: Spacing.two,
  },
});
