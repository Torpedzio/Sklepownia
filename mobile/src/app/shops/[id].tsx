import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Linking, StyleSheet, useWindowDimensions, View } from 'react-native';

import { Page } from '@/components/page';
import { Receipt, type ReceiptRow } from '@/components/receipt';
import { ShopGuidesPanel } from '@/components/shop-guides';
import { ShopLoginGuide } from '@/components/shop-login-guide';
import { StatusBadge } from '@/components/status-badge';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing, WideBreakpoint } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import type { Choice, FormOptions, ShopDetail, ShopStatus } from '@/lib/types';

const IN_PROGRESS = ['pending', 'provisioning'];

export default function ShopScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const theme = useTheme();
  const { width } = useWindowDimensions();
  const wide = width >= WideBreakpoint;
  const { data: shop, error, refresh } = useApiQuery<ShopDetail>(`/shops/${id}/`, {
    refetchInterval: (data) => (data && IN_PROGRESS.includes(data.status) ? 1500 : false),
  });
  const { data: options } = useApiQuery<FormOptions>('/shops/form-options/');
  const notify = useNotify();
  const [busy, setBusy] = useState(false);

  // Announce the end of setup only when it happens on screen, not for shops that were done already.
  const status = shop?.status;
  const name = shop?.name;
  const previousStatus = useRef<ShopStatus>(undefined);
  useEffect(() => {
    const previous = previousStatus.current;
    previousStatus.current = status;
    if (!previous || !IN_PROGRESS.includes(previous)) return;
    if (status === 'active') notify.success(`Sklep „${name}” jest gotowy. Możesz dodawać produkty.`);
    if (status === 'failed') notify.error(`Zakładanie sklepu „${name}” zatrzymało się. Spróbuj ponownie.`);
  }, [status, name, notify]);

  if (!shop) {
    return (
      <Page>
        {error ? <ThemedText themeColor="danger">{error.message}</ThemedText> : <ActivityIndicator style={styles.loader} />}
      </Page>
    );
  }

  async function runAction(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
    } catch (e) {
      notify.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    const confirmed = await confirm(
      'Usunąć sklep?',
      `Sklep „${shop!.name}” zniknie razem z produktami i zamówieniami. Tego nie da się cofnąć.`,
      'Usuń sklep',
    );
    if (confirmed) {
      await runAction(async () => {
        await api(`/shops/${id}/`, { method: 'DELETE' });
        notify.success(`Sklep „${shop!.name}” został usunięty.`);
        router.back();
      });
    }
  }

  const job = shop.provisioning;
  const inProgress = IN_PROGRESS.includes(shop.status);
  const rows: ReceiptRow[] = (job?.steps ?? []).map((step) => ({
    label: step.label,
    status: step.status,
    note: step.error || undefined,
  }));
  const label = (choices: Choice[] | undefined, value: string) => choices?.find((c) => c.value === value)?.label ?? value;
  const config = shop.config;
  const active = shop.status === 'active';

  return (
    <Page>
      <Stack.Screen options={{ title: shop.name }} />

      <View style={styles.header}>
        <ThemedText type="title">{shop.name}</ThemedText>
        <ThemedText themeColor="textSecondary" selectable>
          {shop.url}
        </ThemedText>
        <StatusBadge status={shop.status} label={shop.status_display} />
      </View>

      <View style={[styles.columns, wide && styles.columnsWide]}>
        <View style={[styles.main, wide && styles.flex]}>
          {active ? (
            <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
              <ThemedText type="heading">Twój sklep działa</ThemedText>
              <ThemedText type="small" themeColor="textSecondary">
                Klienci mogą już wchodzić i składać zamówienia. Zanim ogłosisz sklep, przejdź przez pierwsze kroki z
                porad poniżej.
              </ThemedText>
              <View style={styles.actions}>
                <Button title="Otwórz sklep" icon="external" onPress={() => Linking.openURL(shop.url)} />
              </View>
            </View>
          ) : null}

          {shop.status === 'failed' ? (
            <View style={[styles.card, { backgroundColor: theme.dangerMuted, borderColor: theme.danger }]}>
              <ThemedText type="heading">Zakładanie zatrzymało się</ThemedText>
              <ThemedText type="small">Spróbuj ponownie. Zaczniemy od kroku, który się nie udał.</ThemedText>
              <Button
                title="Spróbuj ponownie"
                icon="refresh"
                loading={busy}
                onPress={() =>
                  runAction(async () => {
                    await api(`/shops/${id}/retry/`, { method: 'POST' });
                    notify.success('Wznawiamy zakładanie od kroku, który się nie udał.');
                    await refresh();
                  })
                }
              />
            </View>
          ) : null}

          {inProgress ? (
            <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
              <ThemedText type="heading">To potrwa około dwóch minut</ThemedText>
              <ThemedText type="small" themeColor="textSecondary">
                Możesz zamknąć ten ekran. Sklep zakłada się dalej, a postęp zobaczysz po powrocie.
              </ThemedText>
            </View>
          ) : null}

          <View style={[styles.details, wide && styles.detailsWide]}>
            {job ? (
              <View style={[styles.receipt, wide && styles.receiptWide]}>
                <Receipt
                  title={inProgress ? 'Zakładamy Twój sklep…' : 'Zakładanie sklepu'}
                  subtitle={shop.url.replace(/^https?:\/\//, '')}
                  rows={rows}
                  total={{ label: 'Gotowe kroki', value: `${job.completed_steps}/${job.total_steps}` }}
                  stamp={
                    active
                      ? { text: 'Otwarte', tone: 'success' }
                      : shop.status === 'failed'
                        ? { text: 'Błąd', tone: 'danger' }
                        : undefined
                  }
                />
              </View>
            ) : null}

            <View style={[styles.card, wide && styles.flex, { backgroundColor: theme.surface, borderColor: theme.border }]}>
              <ThemedText type="heading">Ustawienia z formularza</ThemedText>
              <Row label="Branża" value={label(options?.industries, config.industry)} />
              <Row label="Motyw" value={config.template.name} />
              <Row label="Kategorie" value={String(config.category_count)} />
              <Row label="Język" value={label(options?.languages, config.language)} />
              <Row label="Waluta" value={label(options?.currencies, config.currency)} />
              <Row label="Kraj" value={label(options?.countries, config.country)} />
              <Row label="E-mail sklepu" value={config.contact_email} />
            </View>
          </View>

          {active ? <ShopLoginGuide shopId={shop.id} /> : null}
        </View>
      </View>

      <ShopGuidesPanel shopUrl={active ? shop.url : undefined} />

      {!inProgress ? (
        <Button title="Usuń sklep" variant="danger" onPress={handleDelete} disabled={busy} style={styles.delete} />
      ) : null}
    </Page>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <ThemedText type="small" themeColor="textSecondary">
        {label}
      </ThemedText>
      <ThemedText type="smallBold" selectable style={styles.rowValue}>
        {value}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  loader: {
    marginVertical: Spacing.six,
  },
  header: {
    gap: Spacing.two,
  },
  columns: {
    gap: Spacing.four,
  },
  columnsWide: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  main: {
    gap: Spacing.three,
  },
  details: {
    gap: Spacing.three,
  },
  detailsWide: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  receipt: {
    width: '100%',
    maxWidth: 420,
    alignSelf: 'center',
  },
  receiptWide: {
    width: 330,
    alignSelf: 'flex-start',
  },
  delete: {
    alignSelf: 'flex-start',
  },
  card: {
    gap: Spacing.two,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
    marginTop: Spacing.one,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: Spacing.three,
  },
  rowValue: {
    flexShrink: 1,
    textAlign: 'right',
  },
});
