import { Stack } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Linking, StyleSheet, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { Icon } from '@/components/icon';
import { Page } from '@/components/page';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { SwitchRow } from '@/components/ui/switch-row';
import { Radius, Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePushPermission } from '@/hooks/use-push-permission';
import { useTheme } from '@/hooks/use-theme';
import { api } from '@/lib/api';
import { formatTime } from '@/lib/settings-form';
import type { PushBlocker } from '@/lib/push';
import type { PushPreferences } from '@/lib/types';

type Topic = 'new_orders' | 'shops' | 'billing';

const TOPICS: { key: Topic; label: string; description: string }[] = [
  {
    key: 'new_orders',
    label: 'Nowe zamówienia',
    description: 'Gdy w sklepie pojawi się zamówienie. Sklepy sprawdzamy co kilka minut.',
  },
  {
    key: 'shops',
    label: 'Sklepy',
    description: 'Gdy nowy sklep jest gotowy albo jego zakładanie się zatrzyma.',
  },
  {
    key: 'billing',
    label: 'Plan i płatności',
    description: 'Gdy nie uda się pobrać opłaty za plan albo plan się skończy.',
  },
];

const BLOCKED: Record<PushBlocker, string> = {
  web: 'Powiadomienia przychodzą na telefon z aplikacją Sklepownia. Tutaj wybierzesz, o czym mają mówić.',
  'expo-go': 'Ta wersja aplikacji (Expo Go) nie odbiera powiadomień. Działają w aplikacji zainstalowanej ze sklepu.',
  simulator: 'Symulator nie odbiera powiadomień. Sprawdzisz je na telefonie.',
  'no-project': 'Ta wersja aplikacji nie jest połączona z usługą powiadomień.',
};

export default function NotificationsScreen() {
  const theme = useTheme();
  const notify = useNotify();
  const { data, error, refresh } = useApiQuery<PushPreferences>('/push/preferences/');
  const { blocker, permission, canAskAgain, enable } = usePushPermission();
  // Switches answer at once; the server's answer replaces them.
  const [pending, setPending] = useState<Partial<Record<Topic, boolean>>>({});
  const [enabling, setEnabling] = useState(false);

  async function toggle(topic: Topic, value: boolean) {
    setPending((current) => ({ ...current, [topic]: value }));
    try {
      await api('/push/preferences/', { method: 'PATCH', body: { [topic]: value } });
      await refresh();
    } catch (e) {
      notify.error((e as Error).message);
    } finally {
      setPending(({ [topic]: _, ...rest }) => rest);
    }
  }

  async function handleEnable() {
    setEnabling(true);
    try {
      const result = await enable();
      if (result === 'granted') {
        notify.success('Powiadomienia na tym telefonie są włączone.');
        await refresh();
      }
    } catch (e) {
      notify.error((e as Error).message || 'Nie udało się włączyć powiadomień.');
    } finally {
      setEnabling(false);
    }
  }

  return (
    <Page maxWidth={760}>
      <Stack.Screen options={{ title: 'Powiadomienia', ...backArrowOptions('/account', 'Wróć do konta') }} />
      <View style={styles.intro}>
        <ThemedText type="title">Powiadomienia</ThemedText>
        <ThemedText themeColor="textSecondary">
          Powiadomimy Cię na telefonie o tym, co dzieje się w sklepach i z planem. E-maile przychodzą jak dotąd.
        </ThemedText>
      </View>

      <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
        <ThemedText type="heading">Ten telefon</ThemedText>
        {blocker ? (
          <ThemedText type="small" themeColor="textSecondary">
            {BLOCKED[blocker]}
          </ThemedText>
        ) : permission === undefined ? (
          <ActivityIndicator style={styles.start} />
        ) : permission === 'granted' ? (
          <View style={styles.row}>
            <Icon name="check" size={18} color="success" />
            <ThemedText type="small" style={styles.flex}>
              Powiadomienia na tym telefonie są włączone.
            </ThemedText>
          </View>
        ) : canAskAgain ? (
          <>
            <ThemedText type="small" themeColor="textSecondary">
              Włącz je, żeby wiedzieć o nowych zamówieniach bez otwierania aplikacji.
            </ThemedText>
            <Button
              title="Włącz powiadomienia"
              icon="bell"
              loading={enabling}
              onPress={handleEnable}
              style={styles.start}
            />
          </>
        ) : (
          <>
            <ThemedText type="small" themeColor="textSecondary">
              Powiadomienia aplikacji są wyłączone w ustawieniach telefonu. Włączysz je tam.
            </ThemedText>
            <Button
              title="Otwórz ustawienia telefonu"
              icon="admin"
              variant="secondary"
              onPress={() => Linking.openSettings()}
              style={styles.start}
            />
          </>
        )}
      </View>

      <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
        <ThemedText type="heading">O czym powiadamiać</ThemedText>
        {data ? (
          <View>
            {TOPICS.map((topic) => (
              <SwitchRow
                key={topic.key}
                label={topic.label}
                description={topic.description}
                value={pending[topic.key] ?? data[topic.key]}
                onChange={(value) => toggle(topic.key, value)}
              />
            ))}
          </View>
        ) : error ? (
          <ThemedText type="small" themeColor="danger">
            {error.message}
          </ThemedText>
        ) : (
          <ActivityIndicator style={styles.start} />
        )}
        {data ? (
          <ThemedText type="small" themeColor="textSecondary">
            {data.devices.length
              ? `Powiadomienia dostają: ${data.devices.map(describeDevice).join(', ')}.`
              : 'Żaden telefon nie dostaje jeszcze powiadomień.'}
          </ThemedText>
        ) : null}
      </View>
    </Page>
  );
}

/** "Pixel 8 (ostatnio dziś, 09:12)". */
function describeDevice(device: PushPreferences['devices'][number]) {
  return `${device.name || device.platform_display} (ostatnio ${formatTime(device.last_seen_at)})`;
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  intro: {
    gap: Spacing.two,
  },
  card: {
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  start: {
    alignSelf: 'flex-start',
  },
});
