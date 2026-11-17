import { Link } from 'expo-router';
import { useState } from 'react';

import { AuthLayout } from '@/components/auth-layout';
import { Button } from '@/components/ui/button';
import { TextField } from '@/components/ui/text-field';
import { useAuth } from '@/context/auth';
import { useNotify } from '@/context/notifications';
import { ApiError } from '@/lib/api';

export default function SignInScreen() {
  const { signIn } = useAuth();
  const notify = useNotify();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    setSubmitting(true);
    try {
      await signIn(email.trim(), password);
      notify.success('Zalogowano. Twoje sklepy są na miejscu.');
    } catch (e) {
      notify.error(e instanceof ApiError && e.status === 401 ? 'Nieprawidłowy e-mail lub hasło.' : (e as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Zaloguj się" subtitle="Twoje sklepy czekają.">
      <TextField
        label="E-mail"
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoComplete="email"
        keyboardType="email-address"
        textContentType="emailAddress"
      />
      <TextField
        label="Hasło"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoComplete="current-password"
        textContentType="password"
        onSubmitEditing={handleSubmit}
      />
      <Button title="Zaloguj się" size="large" onPress={handleSubmit} loading={submitting} disabled={!email || !password} />
      <Link href={{ pathname: '/reset-password', params: email.trim() ? { email: email.trim() } : {} }} asChild>
        <Button title="Nie pamiętasz hasła?" variant="ghost" />
      </Link>
      <Link href="/sign-up" asChild>
        <Button title="Nie masz konta? Załóż je" variant="ghost" />
      </Link>
    </AuthLayout>
  );
}
