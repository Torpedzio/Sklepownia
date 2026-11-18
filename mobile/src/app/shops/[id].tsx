import { Link, router, Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Linking, StyleSheet, useWindowDimensions, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { Page } from '@/components/page';
import { Receipt, type ReceiptRow } from '@/components/receipt';
import { SalesSummary } from '@/components/sales-summary';
import { ShopGuidesPanel } from '@/components/shop-guides';
import { missingForSales, ShopOverview } from '@/components/shop-overview';
import { TestBadge } from '@/components/shop-sign';
import { StatusBadge } from '@/components/status-badge';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing, WideBreakpoint } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import type { ShopDetail, ShopSettings, ShopStatus } from '@/lib/types';

const IN_PROGRESS = ['pending', 'provisioning'];

export default function ShopScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const theme = useTheme();
  const { width } = useWindowDimensions();
  const wide = width >= WideBreakpoint;
  const {
    data: shop,
    error,
    refresh,
  } = useApiQuery<ShopDetail>(`/shops/${id}/`, {
    refetchInterval: (data) => (data && IN_PROGRESS.includes(data.status) ? 1500 : false),
  });
  // The overview of a running shop shows its settings as last read from the shop.
  const { data: settings } = useApiQuery<ShopSettings>(`/shops/${id}/settings/`, {
    enabled: shop?.status === 'active',
  });
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
        {error ? (
          <ThemedText themeColor="danger">{error.message}</ThemedText>
        ) : (
          <ActivityIndicator style={styles.loader} />
        )}
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
  const active = shop.status === 'active';
  const rows: ReceiptRow[] = (job?.steps ?? []).map((step) => ({
    label: step.label,
    status: step.status,
    note: step.error || undefined,
  }));
  const openSettings = (section?: string) =>
    router.push({
      pathname: '/shops/[id]/settings',
      params: section ? { id: String(shop.id), section } : { id: String(shop.id) },
    });
  const missing = settings ? missingForSales(settings) : [];
  const closed = settings ? !settings.values.availability.is_open : false;

  const receipt = job ? (
    <View style={[styles.receipt, wide && active && settings && styles.receiptWide]}>
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
  ) : null;

  return (
    <Page>
      <Stack.Screen options={{ title: shop.name, ...backArrowOptions('/shops', 'Wróć do listy sklepów') }} />

      <View style={styles.header}>
        <ThemedText type="title">{shop.name}</ThemedText>
        <ThemedText themeColor="textSecondary" selectable>
          {shop.url}
        </ThemedText>
        <View style={styles.badges}>
          <StatusBadge status={shop.status} label={shop.status_display} />
          {shop.is_test ? <TestBadge /> : null}
        </View>
      </View>

      {active ? (
        <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          <ThemedText type="heading">{closed ? 'Sklep jest zamknięty dla klientów' : 'Twój sklep działa'}</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            {closed
              ? 'Klienci widzą stronę „Wkrótce otwarcie”. Otworzysz sklep w ustawieniach, gdy będzie gotowy.'
              : missing.length
                ? `Zanim ogłosisz sklep, ustaw ${missing.join(' i ')}. Bez tego klienci nie złożą zamówienia.`
                : `Klienci mogą już kupować. Produkty dodasz w ${shop.panel_name.replace(/^panel\b/, 'panelu')}, a resztę zmienisz w ustawieniach.`}
          </ThemedText>
          <View style={styles.actions}>
            <Button title="Otwórz sklep" icon="external" onPress={() => Linking.openURL(shop.url)} />
            <Button title="Ustawienia sklepu" icon="filter" variant="secondary" onPress={() => openSettings()} />
            <Button
              title={shop.panel_name.charAt(0).toUpperCase() + shop.panel_name.slice(1)}
              icon="admin"
              variant="secondary"
              onPress={() => openSettings('reczne')}
            />
          </View>
        </View>
      ) : null}

      {active ? <SalesSummary shopId={shop.id} /> : null}

      {shop.status === 'suspended' ? (
        <View style={[styles.card, { backgroundColor: theme.surfaceMuted, borderColor: theme.border }]}>
          <ThemedText type="heading">Sklep niedostępny w obecnym planie</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            Klienci go nie widzą, ale nic z niego nie zniknęło: produkty, zamówienia i ustawienia czekają. Przywrócisz
            go, gdy plan będzie miał miejsce, czyli po zmianie planu albo usunięciu innego sklepu.
          </ThemedText>
          <View style={styles.actions}>
            <Button
              title="Przywróć sklep"
              icon="refresh"
              loading={busy}
              onPress={() =>
                runAction(async () => {
                  await api(`/shops/${id}/resume/`, { method: 'POST' });
                  notify.success(`Sklep „${shop.name}” znów działa.`);
                  await refresh();
                })
              }
            />
            <Link href="/billing/change" asChild>
              <Button title="Zmień plan" icon="filter" variant="secondary" />
            </Link>
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
          <ThemedText type="heading">To potrwa {shop.setup_time}</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            Możesz zamknąć ten ekran. Sklep zakłada się dalej, a postęp zobaczysz po powrocie. Ustawienia sklepu będą
            dostępne, gdy skończymy.
          </ThemedText>
        </View>
      ) : null}

      {/* The receipt sits beside the overview on wide screens; alone it is centered under the cards. */}
      <View style={[styles.columns, wide && settings && active && styles.columnsWide]}>
        {active && settings ? (
          <View style={[styles.overview, wide && styles.flex]}>
            <ThemedText type="heading">Ustawienia w skrócie</ThemedText>
            <ShopOverview shopId={shop.id} settings={settings} />
          </View>
        ) : null}
        {receipt}
      </View>

      {/* The guides walk through the WooCommerce panel. */}
      {shop.platform === 'woocommerce' ? <ShopGuidesPanel shopUrl={active ? shop.url : undefined} /> : null}

      {!inProgress ? (
        <Button title="Usuń sklep" variant="danger" onPress={handleDelete} disabled={busy} style={styles.delete} />
      ) : null}
    </Page>
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
  badges: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
  },
  columns: {
    gap: Spacing.four,
  },
  columnsWide: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  overview: {
    gap: Spacing.three,
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
});
