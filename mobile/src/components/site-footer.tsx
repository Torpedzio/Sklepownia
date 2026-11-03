import { Link } from 'expo-router';
import { Linking, Pressable, StyleSheet, View } from 'react-native';

import { Icon, type IconName } from '@/components/icon';
import { Logo } from '@/components/logo';
import { ThemedText } from '@/components/themed-text';
import { Brand } from '@/constants/brand';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useTheme } from '@/hooks/use-theme';

export function SiteFooter() {
  const { user } = useAuth();
  const theme = useTheme();
  const { contact } = Brand;

  return (
    <View style={[styles.footer, { backgroundColor: theme.surface, borderTopColor: theme.border }]}>
      <View style={styles.inner}>
        <View style={styles.column}>
          <Logo />
          <ThemedText type="small" themeColor="textSecondary" style={styles.tagline}>
            {Brand.tagline}. Zakładamy i utrzymujemy sklepy WooCommerce dla małych firm.
          </ThemedText>
        </View>
        <View style={styles.column}>
          <ThemedText type="smallBold">Kontakt</ThemedText>
          <ContactLine icon="mail" text={contact.email} onPress={() => Linking.openURL(`mailto:${contact.email}`)} />
          <ContactLine icon="phone" text={contact.phone} onPress={() => Linking.openURL(`tel:${contact.phone.replace(/\s/g, '')}`)} />
          <ContactLine icon="clock" text={contact.hours} />
        </View>
        <View style={styles.column}>
          <ThemedText type="smallBold">Na skróty</ThemedText>
          <Link href="/about">
            <ThemedText type="small">Jak to działa</ThemedText>
          </Link>
          <Link href="/contact">
            <ThemedText type="small">Formularz kontaktowy</ThemedText>
          </Link>
          <Link href={user ? '/shops' : '/sign-up'}>
            <ThemedText type="small">{user ? 'Moje sklepy' : 'Załóż konto'}</ThemedText>
          </Link>
        </View>
      </View>
      <ThemedText type="small" themeColor="textSecondary" style={styles.copyright}>
        © {new Date().getFullYear()} {Brand.name}
      </ThemedText>
    </View>
  );
}

function ContactLine({ icon, text, onPress }: { icon: IconName; text: string; onPress?: () => void }) {
  const line = (
    <View style={styles.contactLine}>
      <Icon name={icon} size={16} color="textSecondary" />
      <ThemedText type="small">{text}</ThemedText>
    </View>
  );
  return onPress ? (
    <Pressable onPress={onPress} accessibilityRole="link">
      {line}
    </Pressable>
  ) : (
    line
  );
}

const styles = StyleSheet.create({
  footer: {
    borderTopWidth: 1,
    paddingVertical: Spacing.five,
  },
  inner: {
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
    paddingHorizontal: Spacing.four,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.five,
  },
  column: {
    flexGrow: 1,
    flexBasis: 220,
    gap: Spacing.two,
  },
  tagline: {
    maxWidth: 300,
  },
  contactLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  copyright: {
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
    paddingHorizontal: Spacing.four,
    marginTop: Spacing.five,
  },
});
