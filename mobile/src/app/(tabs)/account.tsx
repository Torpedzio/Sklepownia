import Constants from 'expo-constants';
import { Link } from 'expo-router';
import { useState } from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Icon, type IconName } from '@/components/icon';
import { Page } from '@/components/page';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { TextField } from '@/components/ui/text-field';
import { Fonts, Radius, ReadableWidth, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useNotify } from '@/context/notifications';
import { useTheme } from '@/hooks/use-theme';
import { ApiError } from '@/lib/api';

export default function AccountScreen() {
  const { user, updateProfile, signOut } = useAuth();
  const notify = useNotify();
  const theme = useTheme();
  const [firstName, setFirstName] = useState(user?.first_name ?? '');
  const [lastName, setLastName] = useState(user?.last_name ?? '');
  const [saving, setSaving] = useState(false);

  if (!user) return null;
  const changed = firstName !== user.first_name || lastName !== user.last_name;
  const initial = (user.first_name || user.email).charAt(0).toUpperCase();
  const joined = new Date(user.date_joined).toLocaleDateString('pl-PL', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

  async function handleSave() {
    setSaving(true);
    try {
      await updateProfile({ first_name: firstName.trim(), last_name: lastName.trim() });
      notify.success('Zapisano zmiany w profilu.');
    } catch (e) {
      notify.error(e instanceof ApiError ? e.message : 'Nie udało się zapisać zmian.');
    } finally {
      setSaving(false);
    }
  }

  async function handleSignOut() {
    await signOut();
    notify.success('Wylogowano.');
  }

  return (
    <SafeAreaView
      style={[styles.flex, { backgroundColor: theme.background }]}
      edges={Platform.OS === 'web' ? [] : ['top']}>
      <Page maxWidth={ReadableWidth + 64}>
        <View style={styles.profile}>
          <View style={[styles.avatar, { backgroundColor: theme.accent }]}>
            <ThemedText style={[styles.avatarText, { color: theme.onAccent }]}>{initial}</ThemedText>
          </View>
          <View style={styles.flex}>
            <ThemedText type="subtitle" numberOfLines={1}>
              {[user.first_name, user.last_name].filter(Boolean).join(' ') || 'Twoje konto'}
            </ThemedText>
            <ThemedText themeColor="textSecondary" numberOfLines={1}>
              {user.email}
            </ThemedText>
            <ThemedText type="small" themeColor="textSecondary">
              Z nami od {joined}
            </ThemedText>
          </View>
        </View>

        <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          <ThemedText type="heading">Dane profilu</ThemedText>
          <TextField label="Imię" value={firstName} onChangeText={setFirstName} autoComplete="given-name" />
          <TextField label="Nazwisko" value={lastName} onChangeText={setLastName} autoComplete="family-name" />
          <Button title="Zapisz zmiany" onPress={handleSave} loading={saving} disabled={!changed} />
        </View>

        <View style={[styles.card, styles.links, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          <LinkRow href="/billing" icon="card" label="Plan i płatności" />
          <LinkRow href="/about" icon="help" label="Jak to działa" />
          <LinkRow href="/contact" icon="mail" label="Kontakt" />
        </View>

        <Button title="Wyloguj się" variant="danger" icon="logout" onPress={handleSignOut} />
        <ThemedText type="small" themeColor="textSecondary" style={styles.version}>
          Wersja {Constants.expoConfig?.version}
        </ThemedText>
      </Page>
    </SafeAreaView>
  );
}

function LinkRow({ href, icon, label }: { href: '/billing' | '/about' | '/contact'; icon: IconName; label: string }) {
  return (
    <Link href={href} asChild>
      <Pressable accessibilityRole="link" style={styles.linkRow}>
        <Icon name={icon} size={20} color="textSecondary" />
        <ThemedText style={styles.flex}>{label}</ThemedText>
        <Icon name="chevron" size={18} color="textSecondary" />
      </Pressable>
    </Link>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  profile: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: Radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: {
    fontFamily: Fonts.display,
    fontSize: 28,
    lineHeight: 34,
  },
  card: {
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  links: {
    gap: 0,
    paddingVertical: Spacing.two,
  },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
    paddingVertical: Spacing.three,
  },
  version: {
    textAlign: 'center',
  },
});
