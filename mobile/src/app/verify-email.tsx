import { useEffect, useState } from 'react';
import { StyleSheet } from 'react-native';

import { AuthLayout } from '@/components/auth-layout';
import { Button } from '@/components/ui/button';
import { TextField } from '@/components/ui/text-field';
import { Fonts } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useNotify } from '@/context/notifications';

const RESEND_COOLDOWN_SECONDS = 60;

export default function VerifyEmailScreen() {
  const { user, verifyEmail, resendCode, signOut } = useAuth();
  const notify = useNotify();
  const [code, setCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN_SECONDS);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown(cooldown - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  async function handleVerify() {
    setSubmitting(true);
    try {
      await verifyEmail(code);
      notify.success('Adres e-mail potwierdzony. Możesz założyć pierwszy sklep.');
    } catch (e) {
      notify.error((e as Error).message);
      setSubmitting(false);
    }
  }

  async function handleResend() {
    try {
      await resendCode();
      notify.success(`Wysłaliśmy nowy kod na ${user?.email}.`);
      setCooldown(RESEND_COOLDOWN_SECONDS);
    } catch (e) {
      notify.error((e as Error).message);
    }
  }

  async function handleSignOut() {
    await signOut();
    notify.success('Wylogowano.');
  }

  return (
    <AuthLayout title="Potwierdź e-mail" subtitle={`Wpisz 6-cyfrowy kod, który wysłaliśmy na ${user?.email}.`}>
      <TextField
        label="Kod z wiadomości"
        value={code}
        onChangeText={(text) => setCode(text.replace(/\D/g, '').slice(0, 6))}
        keyboardType="number-pad"
        autoComplete="one-time-code"
        textContentType="oneTimeCode"
        maxLength={6}
        style={styles.codeInput}
        onSubmitEditing={handleVerify}
      />
      <Button title="Potwierdź" size="large" onPress={handleVerify} loading={submitting} disabled={code.length !== 6} />
      <Button
        title={cooldown > 0 ? `Wyślij kod ponownie za ${cooldown} s` : 'Wyślij kod ponownie'}
        variant="secondary"
        onPress={handleResend}
        disabled={cooldown > 0}
      />
      <Button title="Użyj innego konta" variant="ghost" onPress={handleSignOut} />
    </AuthLayout>
  );
}

const styles = StyleSheet.create({
  codeInput: {
    fontFamily: Fonts.displayMedium,
    fontSize: 30,
    letterSpacing: 10,
    textAlign: 'center',
    minHeight: 64,
  },
});
