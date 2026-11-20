import { Link, router, Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Linking, StyleSheet, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { Page } from '@/components/page';
import { Receipt, type ReceiptRow } from '@/components/receipt';
import { SalesSummary } from '@/components/sales-summary';
import { ShopChecklist } from '@/components/shop-checklist';
import { LeaveTeam, TeamCard } from '@/components/shop-team';
import { ShopGuidesPanel } from '@/components/shop-guides';
import { missingForSales, ShopOverview } from '@/components/shop-overview';
import { StaffBadge, TestBadge } from '@/components/shop-sign';
import { ShopStatusBadge } from '@/components/status-badge';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing, WideBreakpoint } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { useWindowDimensions } from '@/hooks/use-window-dimensions';
import { api } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import { formatMoment, panelLocative, panelTitle } from '@/lib/format';
import type { ShopAdminAccess, ShopDetail, ShopSettings, ShopStatus } from '@/lib/types';

const IN_PROGRESS = ['pending', 'provisioning'];
const DOWN_REFRESH = 60_000;

export default function ShopScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const theme = useTheme();
  const { width } = useWindowDimensions();
  const wide = width >= WideBreakpoint;
  const {
    data: shop,
    error,
    isStale,
    refresh,
  } = useApiQuery<ShopDetail>(`/shops/${id}/`, {
    // While the shop is down, poll so the screen updates once it's back.
    refetchInterval: (data) =>
      data && IN_PROGRESS.includes(data.status) ? 1500 : data?.down_since ? DOWN_REFRESH : false,
  });
  // Settings, the panel and the rest of running the shop are the owner's; the staff sees the shop and its sales.
  const owner = shop?.role === 'owner';
  const { data: settings } = useApiQuery<ShopSettings>(`/shops/${id}/settings/`, {
    enabled: shop?.status === 'active' && owner,
  });
  // The tips open the shop's panel, whose address PrestaShop and Magento keep secret.
  const { data: access } = useApiQuery<ShopAdminAccess>(`/shops/${id}/admin-access/`, {
    enabled: shop?.status === 'active' && owner,
  });
  const notify = useNotify();
  const [busy, setBusy] = useState(false);

  // Announce the end of setup only when it happens on screen (a cached copy may still show the setup).
  const status = shop?.status;
  const name = shop?.name;
  const previousStatus = useRef<ShopStatus>(undefined);
  useEffect(() => {
    if (isStale) return;
    const previous = previousStatus.current;
    previousStatus.current = status;
    if (!previous || !IN_PROGRESS.includes(previous)) return;
    if (status === 'active') notify.success(`Sklep „${name}” jest gotowy. Możesz dodawać produkty.`);
    if (status === 'failed') notify.error(`Zakładanie sklepu „${name}” zatrzymało się. Spróbuj ponownie.`);
  }, [status, name, notify, isStale]);

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
  const down = active && Boolean(shop.down_since);
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
          <ShopStatusBadge shop={shop} />
          {shop.is_test ? <TestBadge /> : null}
          {owner ? null : <StaffBadge />}
        </View>
      </View>

      {active ? (
        <View
          style={[
            styles.card,
            down
              ? { backgroundColor: theme.dangerMuted, borderColor: theme.danger }
              : { backgroundColor: theme.surface, borderColor: theme.border },
          ]}>
          <ThemedText type="heading">
            {down
              ? 'Sklep nie działa'
              : closed
                ? 'Sklep jest zamknięty dla klientów'
                : owner
                  ? 'Twój sklep działa'
                  : 'Sklep działa'}
          </ThemedText>
          <ThemedText type="small" themeColor={down ? undefined : 'textSecondary'}>
            {down
              ? `Od ${formatMoment(shop.down_since!)} klienci nie mogą wejść do sklepu. Już to sprawdzamy i damy znać, gdy znowu zadziała.`
              : !owner
                ? 'Sprzedaż sklepu sprawdzisz poniżej. Ustawieniami i panelem sklepu zajmuje się właściciel.'
                : closed
                  ? 'Klienci widzą stronę „Wkrótce otwarcie”. Otworzysz sklep w ustawieniach, gdy będzie gotowy.'
                  : missing.length
                    ? `Zanim ogłosisz sklep, ustaw ${missing.join(' i ')}. Bez tego klienci nie złożą zamówienia.`
                    : `Klienci mogą już kupować. Produkty dodasz w ${panelLocative(shop.panel_name)}, a resztę zmienisz w ustawieniach.`}
          </ThemedText>
          <View style={styles.actions}>
            <Button title="Otwórz sklep" icon="external" onPress={() => Linking.openURL(shop.url)} />
            {owner ? (
              <>
                <Button title="Ustawienia sklepu" icon="filter" variant="secondary" onPress={() => openSettings()} />
                <Button
                  title={panelTitle(shop.panel_name)}
                  icon="admin"
                  variant="secondary"
                  onPress={() => openSettings('reczne')}
                />
              </>
            ) : null}
          </View>
        </View>
      ) : null}

      {active && owner ? <ShopChecklist shop={shop} onOpenSettings={openSettings} /> : null}

      {active ? <SalesSummary shopId={shop.id} /> : null}

      {shop.status === 'suspended' ? (
        <View style={[styles.card, { backgroundColor: theme.surfaceMuted, borderColor: theme.border }]}>
          <ThemedText type="heading">Sklep niedostępny w obecnym planie</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            {owner
              ? 'Klienci go nie widzą, ale nic z niego nie zniknęło: produkty, zamówienia i ustawienia czekają. ' +
                'Przywrócisz go, gdy plan będzie miał miejsce, czyli po zmianie planu albo usunięciu innego sklepu.'
              : 'Klienci go nie widzą, ale nic z niego nie zniknęło. Przywrócić go może właściciel.'}
          </ThemedText>
          {owner ? (
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
          ) : null}
        </View>
      ) : null}

      {shop.status === 'failed' ? (
        <View style={[styles.card, { backgroundColor: theme.dangerMuted, borderColor: theme.danger }]}>
          <ThemedText type="heading">Zakładanie zatrzymało się</ThemedText>
          <ThemedText type="small">
            {owner
              ? 'Spróbuj ponownie. Zaczniemy od kroku, który się nie udał.'
              : 'Ponowić zakładanie może właściciel sklepu.'}
          </ThemedText>
          {owner ? (
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
          ) : null}
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

      {/* Wide screens: the receipt beside the overview; alone, centered under the cards. */}
      <View style={[styles.columns, wide && settings && active && styles.columnsWide]}>
        {active && settings ? (
          <View style={[styles.overview, wide && styles.flex]}>
            <ThemedText type="heading">Ustawienia w skrócie</ThemedText>
            <ShopOverview shopId={shop.id} settings={settings} />
          </View>
        ) : null}
        {receipt}
      </View>

      {owner ? <TeamCard shopId={shop.id} /> : <LeaveTeam shop={shop} />}

      {owner ? <ShopGuidesPanel platform={shop.platform} adminUrl={active ? access?.admin_url : undefined} /> : null}

      {owner && !inProgress ? (
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
