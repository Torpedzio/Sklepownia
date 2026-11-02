import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { TextField } from '@/components/ui/text-field';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useTheme } from '@/hooks/use-theme';

const RESEND_COOLDOWN_SECONDS = 60;

export default function VerifyEmailScreen() {
  const { user, verifyEmail, resendCode, signOut } = useAuth();
  const theme = useTheme();
  const [code, setCode] = useState('');
  const [error, setError] = useState<string>();
  const [info, setInfo] = useState<string>();
  const [submitting, setSubmitting] = useState(false);
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN_SECONDS);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown(cooldown - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  async function handleVerify() {
    setSubmitting(true);
    setError(undefined);
    try {
      await verifyEmail(code);
    } catch (e) {
      setError((e as Error).message);
      setSubmitting(false);
    }
  }

  async function handleResend() {
    setError(undefined);
    try {
      await resendCode();
      setInfo('Wysłaliśmy nowy kod.');
      setCooldown(RESEND_COOLDOWN_SECONDS);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic"
      keyboardShouldPersistTaps="handled">
      <ThemedText>
        Wysłaliśmy 6-cyfrowy kod na <ThemedText type="smallBold">{user?.email}</ThemedText>. Wpisz go poniżej.
      </ThemedText>
      <TextField
        label="Kod weryfikacyjny"
        value={code}
        onChangeText={(text) => setCode(text.replace(/\D/g, '').slice(0, 6))}
        keyboardType="number-pad"
        autoComplete="one-time-code"
        textContentType="oneTimeCode"
        maxLength={6}
        style={styles.codeInput}
        onSubmitEditing={handleVerify}
      />
      {error ? <ThemedText themeColor="danger">{error}</ThemedText> : null}
      {info && !error ? <ThemedText themeColor="success">{info}</ThemedText> : null}
      <Button title="Potwierdź" onPress={handleVerify} loading={submitting} disabled={code.length !== 6} />
      <Button
        title={cooldown > 0 ? `Wyślij kod ponownie (${cooldown} s)` : 'Wyślij kod ponownie'}
        variant="secondary"
        onPress={handleResend}
        disabled={cooldown > 0}
      />
      <Button title="Wyloguj się" variant="secondary" onPress={signOut} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    gap: Spacing.three,
    padding: Spacing.four,
    width: '100%',
    maxWidth: MaxContentWidth / 2,
    alignSelf: 'center',
  },
  codeInput: {
    fontSize: 28,
    letterSpacing: 8,
    textAlign: 'center',
  },
});
