import { Link, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AuthLayout } from '@/components/auth-layout';
import { Icon, type IconName } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { TextField } from '@/components/ui/text-field';
import { Radius, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useNotify } from '@/context/notifications';
import { useTheme } from '@/hooks/use-theme';
import { ApiError } from '@/lib/api';
import type { AccountPurpose } from '@/lib/types';

const PURPOSES: { value: AccountPurpose; icon: IconName; title: string; text: string; subtitle: string }[] = [
  {
    value: 'own_shop',
    icon: 'store',
    title: 'Zakładam sklep',
    text: 'Wybierasz plan, opisujesz sklep, a my go stawiamy.',
    subtitle: 'Potem wybierzesz plan i opiszesz swój sklep, a my go postawimy.',
  },
  {
    value: 'team',
    icon: 'person',
    title: 'Dołączam do zespołu',
    text: 'Pomagasz prowadzić cudzy sklep. Bez planu i płatności.',
    subtitle: 'Właściciel sklepu zaprosi Cię na ten adres e-mail, a zaproszenie pojawi się w aplikacji.',
  },
];

export default function SignUpScreen() {
  const { signUp } = useAuth();
  const notify = useNotify();
  // Links in invitation e-mails carry the invited address and `purpose=team`.
  const params = useLocalSearchParams<{ email?: string; purpose?: string }>();
  const [purpose, setPurpose] = useState<AccountPurpose>(params.purpose === 'team' ? 'team' : 'own_shop');
  const [email, setEmail] = useState(params.email ?? '');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const chosen = PURPOSES.find((option) => option.value === purpose)!;

  async function handleSubmit() {
    setSubmitting(true);
    setFieldErrors({});
    try {
      await signUp(email.trim(), password, purpose);
      notify.success(`Konto założone. Kod potwierdzający wysłaliśmy na ${email.trim().toLowerCase()}.`);
    } catch (e) {
      if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
      notify.error((e as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Załóż konto" subtitle={chosen.subtitle}>
      <View accessibilityRole="radiogroup" accessibilityLabel="Po co zakładasz konto" style={styles.options}>
        {PURPOSES.map((option) => (
          <PurposeOption
            key={option.value}
            {...option}
            selected={option.value === purpose}
            onPress={() => setPurpose(option.value)}
          />
        ))}
      </View>
      <TextField
        label="E-mail"
        value={email}
        onChangeText={setEmail}
        error={fieldErrors.email}
        hint={purpose === 'team' ? 'Ten, na który przyszło albo przyjdzie zaproszenie.' : undefined}
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

type PurposeOptionProps = { icon: IconName; title: string; text: string; selected: boolean; onPress: () => void };

function PurposeOption({ icon, title, text, selected, onPress }: PurposeOptionProps) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityLabel={title}
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[
        styles.option,
        {
          backgroundColor: selected ? theme.primaryMuted : theme.surface,
          borderColor: selected ? theme.primary : theme.border,
        },
      ]}>
      <Icon name={icon} size={22} color={selected ? 'primary' : 'textSecondary'} />
      <View style={styles.optionText}>
        <ThemedText type="smallBold">{title}</ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          {text}
        </ThemedText>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  options: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
  },
  option: {
    flexGrow: 1,
    flexBasis: 200,
    flexDirection: 'row',
    gap: Spacing.two,
    padding: Spacing.three,
    borderRadius: Radius.medium,
    borderWidth: 1.5,
  },
  optionText: {
    flex: 1,
    gap: 2,
  },
});
