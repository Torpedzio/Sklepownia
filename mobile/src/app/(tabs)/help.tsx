import { Link } from 'expo-router';
import { Platform, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { FaqList } from '@/components/faq-list';
import { Page } from '@/components/page';
import { ShopGuidesPanel } from '@/components/shop-guides';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Brand } from '@/constants/brand';
import { Faq, PricingFaq } from '@/constants/content';
import { Radius, ReadableWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export default function HelpScreen() {
  const theme = useTheme();

  return (
    <SafeAreaView
      style={[styles.flex, { backgroundColor: theme.background }]}
      edges={Platform.OS === 'web' ? [] : ['top']}>
      <Page>
        <View style={styles.intro}>
          <ThemedText type="title">Pomoc</ThemedText>
          <ThemedText type="lead" themeColor="textSecondary">
            Najczęstsze sprawy załatwisz w panelu sklepu. Jak się do niego zalogować, znajdziesz na ekranie swojego
            sklepu. Porady poniżej prowadzą po panelu WooCommerce, a na ekranie sklepu każda ma przycisk, który
            otwiera od razu właściwe miejsce. W PrestaShop i Magento te same ustawienia znajdziesz w panelu pod
            podobnymi nazwami.
          </ThemedText>
        </View>

        <ShopGuidesPanel />

        <View style={styles.block}>
          <ThemedText type="subtitle">Pytania i odpowiedzi</ThemedText>
          <FaqList items={Faq} />
        </View>

        <View style={styles.block}>
          <ThemedText type="subtitle">Plany i płatności</ThemedText>
          <FaqList items={PricingFaq} />
        </View>

        <View style={[styles.contact, { backgroundColor: theme.primaryMuted }]}>
          <View style={styles.flex}>
            <ThemedText type="heading">Dalej coś nie działa?</ThemedText>
            <ThemedText themeColor="textSecondary">
              Napisz do nas albo zadzwoń: {Brand.contact.phone}, {Brand.contact.hours.toLowerCase()}.
            </ThemedText>
          </View>
          <Link href="/contact" asChild>
            <Button title="Napisz do nas" icon="mail" />
          </Link>
        </View>
      </Page>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  intro: {
    gap: Spacing.two,
    maxWidth: ReadableWidth,
  },
  block: {
    gap: Spacing.three,
  },
  contact: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
  },
});
