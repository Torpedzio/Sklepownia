import * as Clipboard from 'expo-clipboard';
import { useState } from 'react';
import { ActivityIndicator, Linking, Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Fonts, Radius, Spacing } from '@/constants/theme';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import type { ShopAdminAccess } from '@/lib/types';

/** Step-by-step sign-in to the shop's WordPress panel, with the credentials to copy. */
export function ShopLoginSteps({ shopId }: { shopId: number }) {
  const theme = useTheme();
  const { data: access, error } = useApiQuery<ShopAdminAccess>(`/shops/${shopId}/admin-access/`);
  const [showPassword, setShowPassword] = useState(false);

  return (
    <>
      {error ? <ThemedText themeColor="danger">{error.message}</ThemedText> : null}
      {!access && !error ? <ActivityIndicator /> : null}

      {access ? (
        <View style={styles.steps}>
          <Step number={1} title="Otwórz stronę logowania">
            <Button title="Otwórz panel sklepu" icon="external" onPress={() => Linking.openURL(access.admin_url)} />
            <ThemedText type="small" themeColor="textSecondary" selectable>
              {access.admin_url}
            </ThemedText>
          </Step>
          <Step number={2} title="W polu „Nazwa użytkownika lub adres email” wpisz">
            <Secret value={access.username} />
          </Step>
          <Step number={3} title="W polu „Hasło” wpisz">
            <Secret value={access.password} hidden={!showPassword} onToggle={() => setShowPassword((v) => !v)} />
          </Step>
          <Step number={4} title="Kliknij „Zaloguj się”">
            <ThemedText type="small" themeColor="textSecondary">
              Najważniejsze są Produkty i WooCommerce w menu po lewej.
            </ThemedText>
          </Step>
        </View>
      ) : null}

      <View style={[styles.note, { borderTopColor: theme.border }]}>
        <ThemedText type="small" themeColor="textSecondary">
          Zapisz hasło w przeglądarce albo menedżerze haseł. Jeśli zmienisz je w panelu, tutaj dalej zobaczysz to
          pierwotne.
        </ThemedText>
      </View>
    </>
  );
}

function Step({ number, title, children }: { number: number; title: string; children: React.ReactNode }) {
  const theme = useTheme();
  return (
    <View style={styles.step}>
      <View style={[styles.number, { backgroundColor: theme.primary }]}>
        <ThemedText style={[styles.numberText, { color: theme.onPrimary }]}>{number}</ThemedText>
      </View>
      <View style={styles.stepBody}>
        <ThemedText type="smallBold">{title}</ThemedText>
        {children}
      </View>
    </View>
  );
}

function Secret({ value, hidden = false, onToggle }: { value: string; hidden?: boolean; onToggle?: () => void }) {
  const theme = useTheme();
  const [copied, setCopied] = useState(false);

  async function copy() {
    await Clipboard.setStringAsync(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <View style={[styles.secret, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <ThemedText style={styles.secretValue} selectable={!hidden} numberOfLines={1}>
        {hidden ? '•'.repeat(12) : value}
      </ThemedText>
      {onToggle ? (
        <Pressable onPress={onToggle} accessibilityRole="button" hitSlop={6}>
          <ThemedText type="smallBold" themeColor="primary">
            {hidden ? 'Pokaż' : 'Ukryj'}
          </ThemedText>
        </Pressable>
      ) : null}
      <Pressable onPress={copy} accessibilityRole="button" accessibilityLabel="Kopiuj" hitSlop={6}>
        <ThemedText type="smallBold" themeColor={copied ? 'success' : 'primary'}>
          {copied ? 'Skopiowano' : 'Kopiuj'}
        </ThemedText>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  steps: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    columnGap: Spacing.five,
    rowGap: Spacing.three,
  },
  step: {
    // Two columns on wide screens, one on phones.
    flexBasis: '40%',
    minWidth: 240,
    flexGrow: 1,
    flexDirection: 'row',
    gap: Spacing.three,
  },
  number: {
    width: 26,
    height: 26,
    borderRadius: Radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  numberText: {
    fontFamily: Fonts.display,
    fontSize: 13,
    lineHeight: 16,
  },
  stepBody: {
    flex: 1,
    gap: Spacing.two,
  },
  secret: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
    minHeight: 44,
    paddingHorizontal: Spacing.three,
    borderRadius: Radius.medium,
    borderWidth: 1,
  },
  secretValue: {
    flex: 1,
    fontFamily: Fonts.mono,
    fontSize: 15,
  },
  note: {
    paddingTop: Spacing.three,
    borderTopWidth: 1,
  },
});
