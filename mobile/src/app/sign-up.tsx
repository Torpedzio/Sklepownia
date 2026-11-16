import { Link } from 'expo-router';
import { useState } from 'react';

import { AuthLayout } from '@/components/auth-layout';
import { Button } from '@/components/ui/button';
import { TextField } from '@/components/ui/text-field';
import { useAuth } from '@/context/auth';
import { useNotify } from '@/context/notifications';
import { ApiError } from '@/lib/api';

export default function SignUpScreen() {
  const { signUp } = useAuth();
  const notify = useNotify();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    setSubmitting(true);
    setFieldErrors({});
    try {
      await signUp(email.trim(), password);
      notify.success(`Konto założone. Kod potwierdzający wysłaliśmy na ${email.trim().toLowerCase()}.`);
    } catch (e) {
      if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
      notify.error((e as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Załóż konto" subtitle="Potem wybierzesz plan i opiszesz swój sklep, a my go postawimy.">
      <TextField
        label="E-mail"
        value={email}
        onChangeText={setEmail}
        error={fieldErrors.email}
        autoCapitalize="none"
        autoComplete="email"
        keyboardType="email-address"
        textContentType="emailAddress"
      />
      <TextField
        label="Hasło"
        value={password}
        onChangeText={setPassword}
        error={fieldErrors.password}
        hint="Co najmniej 8 znaków, nie same cyfry."
        secureTextEntry
        autoComplete="new-password"
        textContentType="newPassword"
        onSubmitEditing={handleSubmit}
      />
      <Button
        title="Załóż konto"
        size="large"
        onPress={handleSubmit}
        loading={submitting}
        disabled={!email || !password}
      />
      <Link href="/sign-in" asChild>
        <Button title="Masz już konto? Zaloguj się" variant="ghost" />
      </Link>
    </AuthLayout>
  );
}
