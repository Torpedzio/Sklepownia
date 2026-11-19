import { useState } from 'react';
import { ActivityIndicator, Linking, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Fonts, Radius, Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api, ApiError } from '@/lib/api';
import type { ShopAdminAccess } from '@/lib/types';

/** Sign-in steps for the admin panel. Credentials are never shown here: they go by e-mail, which this can resend. */
export function ShopLoginSteps({ shopId }: { shopId: number }) {
  const theme = useTheme();
  const notify = useNotify();
  const { data: access, error } = useApiQuery<ShopAdminAccess>(`/shops/${shopId}/admin-access/`);
  const [sending, setSending] = useState(false);

  async function sendAgain() {
    setSending(true);
    try {
      const sent = await api<ShopAdminAccess>(`/shops/${shopId}/send-admin-access/`, { method: 'POST' });
      notify.success(`Wysłaliśmy dane logowania na ${sent.sent_to}.`);
    } catch (e) {
      notify.error(
        e instanceof ApiError && e.status === 429
          ? 'Dane wysłaliśmy już kilka razy. Spróbuj ponownie za godzinę.'
          : (e as Error).message,
      );
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      {error ? <ThemedText themeColor="danger">{error.message}</ThemedText> : null}
      {!access && !error ? <ActivityIndicator /> : null}

      {access ? (
        <View style={styles.steps}>
          <Step number={1} title="Otwórz stronę logowania">
            <Button title="Otwórz panel sklepu" icon="external" onPress={() => Linking.openURL(access.admin_url)} />
          </Step>
          <Step number={2} title="Wpisz login i hasło z wiadomości e-mail">
            <Button
              title="Wyślij dane ponownie"
              icon="mail"
              variant="secondary"
              loading={sending}
              onPress={sendAgain}
              style={styles.start}
            />
          </Step>
        </View>
      ) : null}

      <View style={[styles.note, { borderTopColor: theme.border }]}>
        <ThemedText type="small" themeColor="textSecondary">
          Hasła nie pokazujemy w aplikacji, żeby nikt nie podejrzał go na ekranie. Zapisz je w przeglądarce albo
          menedżerze haseł. Zapomniane hasło zmienisz w sekcji „Bezpieczeństwo”, a nowe przyjdzie e-mailem.
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
  start: {
    alignSelf: 'flex-start',
  },
  note: {
    paddingTop: Spacing.three,
    borderTopWidth: 1,
  },
});
