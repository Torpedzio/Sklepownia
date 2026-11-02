import { Link } from 'expo-router';
import { useState } from 'react';
import { ScrollView, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Button } from '@/components/ui/button';
import { TextField } from '@/components/ui/text-field';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { ApiError } from '@/lib/api';

export default function SignInScreen() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    setSubmitting(true);
    setError(undefined);
    try {
      await signIn(email.trim(), password);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 401 ? 'Nieprawidłowy e-mail lub hasło.' : (e as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <ThemedView style={styles.flex}>
      <SafeAreaView style={styles.flex}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <ThemedText type="subtitle">Twój sklep{'\n'}w kilka minut</ThemedText>
          <ThemedText themeColor="textSecondary">Zaloguj się, aby zarządzać swoimi sklepami.</ThemedText>

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
          {error ? <ThemedText themeColor="danger">{error}</ThemedText> : null}

          <Button title="Zaloguj się" onPress={handleSubmit} loading={submitting} disabled={!email || !password} />
          <Link href="/sign-up" asChild>
            <Button title="Nie masz konta? Zarejestruj się" variant="secondary" />
          </Link>
        </ScrollView>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  content: {
    flexGrow: 1,
    justifyContent: 'center',
    gap: Spacing.three,
    padding: Spacing.four,
    width: '100%',
    maxWidth: MaxContentWidth / 2,
    alignSelf: 'center',
  },
});
