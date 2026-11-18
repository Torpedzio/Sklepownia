import { Link, usePathname, type Href } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { Awning } from '@/components/awning';
import { Icon } from '@/components/icon';
import { Logo } from '@/components/logo';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useTheme } from '@/hooks/use-theme';
import { useWindowDimensions } from '@/hooks/use-window-dimensions';

/** Header of the public pages: awning on top, logo, links and the sign-in button. */
export function SiteHeader() {
  const { user } = useAuth();
  const { width } = useWindowDimensions();
  // Below this width the text links don't fit next to the logo and the button.
  const compact = width < 760;

  return (
    <View>
      <Awning />
      <View style={styles.bar}>
        <Link href="/" asChild>
          <Pressable accessibilityRole="link">
            <Logo />
          </Pressable>
        </Link>
        <View style={styles.nav}>
          {compact ? null : (
            <>
              <NavLink href="/" label="Strona główna" />
              <NavLink href="/about" label="Jak to działa" />
              <NavLink href="/pricing" label="Cennik" />
              <NavLink href="/contact" label="Kontakt" />
              {user ? <NavLink href="/account" label="Konto" /> : null}
            </>
          )}
          {/* Narrow screens keep only the account icon next to the main button. */}
          {compact && user ? (
            <Link href="/account" asChild>
              <Pressable accessibilityRole="link" accessibilityLabel="Konto" hitSlop={Spacing.two} style={styles.link}>
                <Icon name="person" size={26} />
              </Pressable>
            </Link>
          ) : null}
          <Link href={user ? '/shops' : '/sign-in'} asChild>
            <Button title={user ? 'Moje sklepy' : 'Zaloguj się'} variant="secondary" />
          </Link>
        </View>
      </View>
    </View>
  );
}

/** A text link underlined with a thin line while its page is open. */
function NavLink({ href, label }: { href: Href & string; label: string }) {
  const theme = useTheme();
  const current = usePathname() === href;
  return (
    <Link href={href} asChild>
      <Pressable accessibilityRole="link" accessibilityState={{ selected: current }} style={styles.link}>
        <ThemedText type="smallBold">{label}</ThemedText>
        {/* Always laid out, so the current link doesn't sit higher than the others. */}
        <View style={[styles.underline, { backgroundColor: current ? theme.text : 'transparent' }]} />
      </Pressable>
    </Link>
  );
}

const styles = StyleSheet.create({
  bar: {
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.four,
    paddingVertical: Spacing.three,
    gap: Spacing.three,
  },
  nav: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.four,
  },
  link: {
    paddingVertical: Spacing.two,
  },
  underline: {
    height: 1.5,
    marginTop: Spacing.one,
  },
});
