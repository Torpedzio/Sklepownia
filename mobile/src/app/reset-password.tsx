import { Link, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';

import { AuthLayout } from '@/components/auth-layout';
import { Button } from '@/components/ui/button';
import { CODE_LENGTH, CodeField } from '@/components/ui/code-field';
import { TextField } from '@/components/ui/text-field';
import { useAuth } from '@/context/auth';
import { useNotify } from '@/context/notifications';
import { ApiError } from '@/lib/api';

const RESEND_COOLDOWN_SECONDS = 60;

/** Forgotten password: the address first, then the code from the e-mail and a new password. */
export default function ResetPasswordScreen() {
  const params = useLocalSearchParams<{ email?: string }>();
  const { requestPasswordReset, resetPassword } = useAuth();
  const notify = useNotify();
  const [email, setEmail] = useState(params.email ?? '');
  // The address the code went to; until then the screen asks for it.
  const [sentTo, setSentTo] = useState<string>();
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown(cooldown - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  async function sendCode() {
    const address = email.trim().toLowerCase();
    setSubmitting(true);
    setFieldErrors({});
    try {
      await requestPasswordReset(address);
      if (sentTo) notify.success('Jeśli to adres konta, nowy kod jest w drodze. Działa tylko najnowszy.');
      setSentTo(address);
      setCooldown(RESEND_COOLDOWN_SECONDS);
    } catch (e) {
      if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
      notify.error((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReset() {
    if (!sentTo) return;
    setSubmitting(true);
    setFieldErrors({});
    try {
      await resetPassword(sentTo, code, password);
      notify.success('Nowe hasło ustawione. Na innych urządzeniach zaloguj się ponownie.');
    } catch (e) {
      // The reason (wrong code, weak password) is clearer than a general "check the form".
      const fields = e instanceof ApiError ? e.fieldErrors : {};
      setFieldErrors(fields);
      notify.error(Object.values(fields)[0] ?? (e as Error).message);
      setSubmitting(false);
    }
  }

  function changeAddress() {
    setSentTo(undefined);
    setCode('');
    setFieldErrors({});
  }

  if (!sentTo) {
    return (
      <AuthLayout title="Nie pamiętasz hasła?" subtitle="Podaj adres konta. Wyślemy na niego kod do ustawienia nowego hasła.">
        <TextField
          label="E-mail"
          value={email}
          onChangeText={setEmail}
          error={fieldErrors.email}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          textContentType="emailAddress"
          onSubmitEditing={sendCode}
        />
        <Button title="Wyślij kod" size="large" onPress={sendCode} loading={submitting} disabled={!email.trim()} />
        <Link href="/sign-in" asChild>
          <Button title="Wróć do logowania" variant="ghost" />
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Ustaw nowe hasło"
      subtitle={`Jeśli ${sentTo} to adres konta, za chwilę dostaniesz na niego kod. Nie widzisz wiadomości? Zajrzyj do spamu.`}>
      <CodeField value={code} onChangeText={setCode} error={fieldErrors.code} />
      <TextField
        label="Nowe hasło"
        value={password}
        onChangeText={setPassword}
        error={fieldErrors.new_password}
        hint="Co najmniej 8 znaków, nie same cyfry."
        secureTextEntry
        autoComplete="new-password"
        textContentType="newPassword"
        onSubmitEditing={handleReset}
      />
      <Button
        title="Ustaw hasło i zaloguj się"
        size="large"
        onPress={handleReset}
        loading={submitting}
        disabled={code.length !== CODE_LENGTH || !password}
      />
      <Button
        title={cooldown > 0 ? `Wyślij kod ponownie za ${cooldown} s` : 'Wyślij kod ponownie'}
        variant="secondary"
        onPress={sendCode}
        disabled={cooldown > 0 || submitting}
      />
      <Button title="Zmień adres e-mail" variant="ghost" onPress={changeAddress} />
    </AuthLayout>
  );
}
