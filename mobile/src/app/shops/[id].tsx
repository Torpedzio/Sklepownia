import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, View } from 'react-native';

import { StatusBadge } from '@/components/status-badge';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Button } from '@/components/ui/button';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import type { ProvisioningStep, ShopDetail } from '@/lib/types';

const STEP_ICON: Record<ProvisioningStep['status'], string> = {
  pending: '○',
  running: '◐',
  done: '✓',
  failed: '✕',
};

export default function ShopScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const theme = useTheme();
  const { data: shop, error, refresh } = useApiQuery<ShopDetail>(`/shops/${id}/`, {
    refetchInterval: (data) => (data?.status === 'pending' || data?.status === 'provisioning' ? 1500 : false),
  });
  const [actionError, setActionError] = useState<string>();
  const [busy, setBusy] = useState(false);

  if (!shop) {
    return error ? (
      <ThemedText themeColor="danger" style={styles.content}>
        {error.message}
      </ThemedText>
    ) : (
      <ActivityIndicator style={styles.loader} />
    );
  }

  async function runAction(action: () => Promise<unknown>) {
    setBusy(true);
    setActionError(undefined);
    try {
      await action();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    const confirmed = await confirm('Usunąć sklep?', `Sklep „${shop!.name}” zostanie usunięty.`, 'Usuń');
    if (confirmed) {
      await runAction(async () => {
        await api(`/shops/${id}/`, { method: 'DELETE' });
        router.back();
      });
    }
  }

  const job = shop.provisioning;
  const progress = job && job.total_steps ? job.completed_steps / job.total_steps : 0;
  const inProgress = shop.status === 'pending' || shop.status === 'provisioning';

  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic">
      <Stack.Screen options={{ title: shop.name }} />

      <View style={styles.header}>
        <StatusBadge status={shop.status} label={shop.status_display} />
        <ThemedText type="small" themeColor="textSecondary" selectable>
          {shop.url}
        </ThemedText>
      </View>

      {job ? (
        <ThemedView type="backgroundElement" style={styles.card}>
          <View style={styles.progressHeader}>
            <ThemedText type="smallBold">{inProgress ? 'Zakładamy Twój sklep…' : 'Zakładanie sklepu'}</ThemedText>
            <ThemedText type="small" themeColor="textSecondary">
              {job.completed_steps}/{job.total_steps}
            </ThemedText>
          </View>
          <View style={[styles.progressTrack, { backgroundColor: theme.backgroundSelected }]}>
            <View
              style={[
                styles.progressFill,
                { width: `${progress * 100}%`, backgroundColor: shop.status === 'failed' ? theme.danger : theme.primary },
              ]}
            />
          </View>
          {job.steps.map((step) => (
            <View key={step.key} style={styles.step}>
              <ThemedText
                style={styles.stepIcon}
                themeColor={step.status === 'done' ? 'success' : step.status === 'failed' ? 'danger' : step.status === 'running' ? 'primary' : 'textSecondary'}>
                {STEP_ICON[step.status]}
              </ThemedText>
              <View style={styles.flex}>
                <ThemedText type="small" themeColor={step.status === 'pending' ? 'textSecondary' : 'text'}>
                  {step.label}
                </ThemedText>
                {step.error ? (
                  <ThemedText type="small" themeColor="danger">
                    {step.error}
                  </ThemedText>
                ) : null}
              </View>
            </View>
          ))}
        </ThemedView>
      ) : null}

      <ThemedView type="backgroundElement" style={styles.card}>
        <ThemedText type="smallBold">Konfiguracja</ThemedText>
        <ConfigRow label="Szablon" value={shop.config.template.name} />
        <ConfigRow label="Kategorie" value={String(shop.config.category_count)} />
        <ConfigRow label="Język" value={shop.config.language} />
        <ConfigRow label="Waluta" value={shop.config.currency} />
        <ConfigRow label="Kraj" value={shop.config.country} />
        <ConfigRow label="E-mail kontaktowy" value={shop.config.contact_email} />
      </ThemedView>

      {actionError ? <ThemedText themeColor="danger">{actionError}</ThemedText> : null}
      {shop.status === 'failed' ? (
        <Button
          title="Spróbuj ponownie"
          loading={busy}
          onPress={() => runAction(async () => {
            await api(`/shops/${id}/retry/`, { method: 'POST' });
            await refresh();
          })}
        />
      ) : null}
      {!inProgress ? <Button title="Usuń sklep" variant="danger" onPress={handleDelete} disabled={busy} /> : null}
    </ScrollView>
  );
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.configRow}>
      <ThemedText type="small" themeColor="textSecondary">
        {label}
      </ThemedText>
      <ThemedText type="small">{value}</ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  loader: {
    flex: 1,
  },
  content: {
    gap: Spacing.three,
    padding: Spacing.three,
    paddingBottom: Spacing.six,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
  header: {
    gap: Spacing.two,
  },
  card: {
    gap: Spacing.two,
    padding: Spacing.three,
    borderRadius: Spacing.three,
  },
  progressHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  progressTrack: {
    height: 6,
    borderRadius: 3,
    overflow: 'hidden',
    marginBottom: Spacing.two,
  },
  progressFill: {
    height: '100%',
    borderRadius: 3,
  },
  step: {
    flexDirection: 'row',
    gap: Spacing.two,
  },
  stepIcon: {
    width: 20,
    textAlign: 'center',
  },
  configRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: Spacing.three,
  },
});
