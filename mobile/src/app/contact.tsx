import { useState } from 'react';
import { Linking, Platform, Pressable, StyleSheet, useWindowDimensions, View } from 'react-native';

import { Icon, type IconName } from '@/components/icon';
import { Page } from '@/components/page';
import { SiteFooter } from '@/components/site-footer';
import { SiteHeader } from '@/components/site-header';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { ChipSelect } from '@/components/ui/chip-select';
import { TextField } from '@/components/ui/text-field';
import { Brand } from '@/constants/brand';
import { Radius, Spacing, WideBreakpoint } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useNotify } from '@/context/notifications';
import { useTheme } from '@/hooks/use-theme';
import { api, ApiError } from '@/lib/api';

const TOPICS = [
  { value: 'question', label: 'Pytanie' },
  { value: 'shop_problem', label: 'Problem ze sklepem' },
  { value: 'billing', label: 'Płatności i faktury' },
  { value: 'other', label: 'Inne' },
];

export default function ContactScreen() {
  const { user } = useAuth();
  const notify = useNotify();
  const theme = useTheme();
  const { width } = useWindowDimensions();
  const wide = width >= WideBreakpoint;
  const web = Platform.OS === 'web';
  const { contact } = Brand;

  const [form, setForm] = useState({
    name: [user?.first_name, user?.last_name].filter(Boolean).join(' '),
    email: user?.email ?? '',
    topic: 'question',
    message: '',
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [sending, setSending] = useState(false);
  const [sentTo, setSentTo] = useState<string>();

  function update(key: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
    setFieldErrors(({ [key]: _, ...rest }) => rest);
  }

  async function handleSend() {
    setSending(true);
    try {
      await api('/contact/', { method: 'POST', body: form, auth: !!user });
      setSentTo(form.email);
      notify.success('Wiadomość wysłana.');
    } catch (e) {
      if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
      notify.error(e instanceof ApiError && e.status === 429 ? 'Wysłano już kilka wiadomości. Spróbuj za godzinę.' : (e as Error).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <Page top={web ? <SiteHeader /> : undefined} bottom={web ? <SiteFooter /> : undefined}>
      <View style={[styles.layout, wide && styles.layoutWide]}>
        <View style={[styles.info, wide && styles.infoWide]}>
          <ThemedText type="title">Napisz do nas</ThemedText>
          <ThemedText type="lead" themeColor="textSecondary">
            Pytanie przed założeniem sklepu, kłopot z działającym sklepem albo pomysł, czego brakuje w aplikacji.
            Czytamy każdą wiadomość.
          </ThemedText>
          <View style={styles.details}>
            <Detail icon="mail" label="E-mail" value={contact.email} onPress={() => Linking.openURL(`mailto:${contact.email}`)} />
            <Detail icon="phone" label="Telefon" value={contact.phone} onPress={() => Linking.openURL(`tel:${contact.phone.replace(/\s/g, '')}`)} />
            <Detail icon="clock" label="Godziny" value={contact.hours} />
            <Detail icon="pin" label="Adres" value={contact.address} />
          </View>
        </View>

        <View style={[styles.form, wide && styles.flex, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          {sentTo ? (
            <View style={styles.sent}>
              <View style={[styles.sentIcon, { backgroundColor: theme.primaryMuted }]}>
                <Icon name="check" size={28} color="primary" />
              </View>
              <ThemedText type="subtitle">Wiadomość wysłana</ThemedText>
              <ThemedText themeColor="textSecondary">Odpowiemy na adres {sentTo}.</ThemedText>
              <Button
                title="Napisz kolejną wiadomość"
                variant="secondary"
                onPress={() => {
                  setSentTo(undefined);
                  update('message', '');
                }}
              />
            </View>
          ) : (
            <>
              <TextField label="Imię i nazwisko" value={form.name} onChangeText={(v) => update('name', v)} error={fieldErrors.name} autoComplete="name" />
              <TextField
                label="E-mail do odpowiedzi"
                value={form.email}
                onChangeText={(v) => update('email', v)}
                error={fieldErrors.email}
                autoCapitalize="none"
                autoComplete="email"
                keyboardType="email-address"
              />
              <ChipSelect label="Temat" options={TOPICS} value={form.topic} onChange={(v) => update('topic', v)} />
              <TextField
                label="Wiadomość"
                value={form.message}
                onChangeText={(v) => update('message', v)}
                error={fieldErrors.message}
                multiline
                placeholder="Opisz, w czym możemy pomóc"
              />
              <Button
                title="Wyślij wiadomość"
                onPress={handleSend}
                loading={sending}
                disabled={!form.name || !form.email || form.message.trim().length < 10}
              />
            </>
          )}
        </View>
      </View>
    </Page>
  );
}

function Detail({ icon, label, value, onPress }: { icon: IconName; label: string; value: string; onPress?: () => void }) {
  const theme = useTheme();
  const content = (
    <View style={styles.detail}>
      <View style={[styles.detailIcon, { backgroundColor: theme.accentMuted }]}>
        <Icon name={icon} size={18} />
      </View>
      <View>
        <ThemedText type="small" themeColor="textSecondary">
          {label}
        </ThemedText>
        <ThemedText type={onPress ? 'link' : 'default'}>{value}</ThemedText>
      </View>
    </View>
  );
  return onPress ? (
    <Pressable onPress={onPress} accessibilityRole="link">
      {content}
    </Pressable>
  ) : (
    content
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  layout: {
    gap: Spacing.five,
  },
  layoutWide: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  info: {
    gap: Spacing.three,
  },
  infoWide: {
    width: 400,
  },
  details: {
    gap: Spacing.three,
    marginTop: Spacing.two,
  },
  detail: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
  },
  detailIcon: {
    width: 40,
    height: 40,
    borderRadius: Radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  form: {
    gap: Spacing.four,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  sent: {
    alignItems: 'flex-start',
    gap: Spacing.three,
    paddingVertical: Spacing.four,
  },
  sentIcon: {
    width: 56,
    height: 56,
    borderRadius: Radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
