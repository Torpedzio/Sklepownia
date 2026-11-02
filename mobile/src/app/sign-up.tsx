import { useState } from 'react';
import { ScrollView, StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { TextField } from '@/components/ui/text-field';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { ApiError } from '@/lib/api';
import { useTheme } from '@/hooks/use-theme';

export default function SignUpScreen() {
  const { signUp } = useAuth();
  const theme = useTheme();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    setSubmitting(true);
    setError(undefined);
    setFieldErrors({});
    try {
      await signUp(email.trim(), password);
    } catch (e) {
      if (e instanceof ApiError && Object.keys(e.fieldErrors).length) setFieldErrors(e.fieldErrors);
      else setError((e as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic"
      keyboardShouldPersistTaps="handled">
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
      {error ? <ThemedText themeColor="danger">{error}</ThemedText> : null}
      <Button title="Załóż konto" onPress={handleSubmit} loading={submitting} disabled={!email || !password} />
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
});
