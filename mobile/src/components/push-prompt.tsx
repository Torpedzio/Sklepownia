import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { Icon } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { usePushPermission } from '@/hooks/use-push-permission';
import { useTheme } from '@/hooks/use-theme';

// "Nie teraz" holds until the app is closed.
let dismissed = false;

/** Shown only while the phone hasn't been asked yet. */
export function PushPrompt() {
  const theme = useTheme();
  const notify = useNotify();
  const { blocker, permission, canAskAgain, enable } = usePushPermission();
  const [hidden, setHidden] = useState(dismissed);
  const [busy, setBusy] = useState(false);

  if (blocker || hidden || permission !== 'undetermined' || !canAskAgain) return null;

  async function handleEnable() {
    setBusy(true);
    try {
      if ((await enable()) === 'granted') notify.success('Powiadomimy Cię o nowych zamówieniach.');
    } catch (e) {
      notify.error((e as Error).message || 'Nie udało się włączyć powiadomień.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={[styles.card, { backgroundColor: theme.primaryMuted, borderColor: theme.primary }]}>
      <View style={styles.row}>
        <Icon name="bell" size={20} color="primary" />
        <ThemedText type="heading" style={styles.flex}>
          Wiedz o zamówieniach od razu
        </ThemedText>
      </View>
      <ThemedText type="small">
        Powiadomimy Cię na tym telefonie, gdy w sklepie pojawi się nowe zamówienie. Wyłączysz to w ustawieniach konta.
      </ThemedText>
      <View style={styles.row}>
        <Button title="Włącz powiadomienia" icon="bell" loading={busy} onPress={handleEnable} />
        <Button
          title="Nie teraz"
          variant="ghost"
          onPress={() => {
            dismissed = true;
            setHidden(true);
          }}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  card: {
    gap: Spacing.two,
    padding: Spacing.three,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: Spacing.two,
  },
});
