import { Link } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Platform, Pressable, RefreshControl, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Awning } from '@/components/awning';
import { Icon } from '@/components/icon';
import { Invitations } from '@/components/invitations';
import { Logo } from '@/components/logo';
import { isShopLimitReached, NewShopButton, paidShopCount } from '@/components/new-shop-button';
import { Page } from '@/components/page';
import { ShopSign } from '@/components/shop-sign';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api } from '@/lib/api';
import { plural } from '@/lib/plural';
import { fetchQuery } from '@/lib/query-cache';
import type { Shop } from '@/lib/types';

const IN_PROGRESS = ['pending', 'provisioning'];

export default function DashboardScreen() {
  const { user } = useAuth();
  const theme = useTheme();
  const {
    data: shops,
    error,
    isLoading,
    isRefreshing,
    refresh,
  } = useApiQuery<Shop[]>('/shops/', {
    refetchInterval: (data) => (data?.some((shop) => IN_PROGRESS.includes(shop.status)) ? 3000 : false),
  });
  const active = shops?.filter((shop) => shop.status === 'active').length ?? 0;
  const paidShops = paidShopCount(shops);
  const limitReached = !!user?.plan && isShopLimitReached(user.shop_limit, paidShops);
  // Signed up to join others' teams: no plan suggestions, just the wait for an invitation.
  const joining = user?.purpose === 'team' && !user.plan;

  return (
    <SafeAreaView
      style={[styles.flex, { backgroundColor: theme.background }]}
      edges={Platform.OS === 'web' ? [] : ['top']}>
      <Page refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={refresh} />}>
        {Platform.OS === 'web' ? null : (
          <Link href="/" asChild>
            <Pressable accessibilityRole="link" accessibilityLabel="Strona główna" style={styles.homeLink}>
              <Logo />
            </Pressable>
          </Link>
        )}
        <View style={styles.header}>
          <View style={styles.headerText}>
            {user?.first_name ? (
              <ThemedText type="smallBold" themeColor="textSecondary">
                Dzień dobry, {user.first_name}
              </ThemedText>
            ) : null}
            <ThemedText type="title">Twoje sklepy</ThemedText>
            {shops?.length ? (
              <ThemedText themeColor="textSecondary">
                {shops.length} {plural(shops.length, ['sklep', 'sklepy', 'sklepów'])}, w tym {active}{' '}
                {plural(active, ['otwarty', 'otwarte', 'otwartych'])}.{limitReached ? ' To limit Twojego planu.' : ''}
              </ThemedText>
            ) : null}
          </View>
          {shops?.length && !joining ? <NewShopButton title="Nowy sklep" icon="plus" shopCount={paidShops} /> : null}
        </View>

        <Invitations onJoined={refresh} poll={joining && shops?.length === 0} />

        {error ? <ThemedText themeColor="danger">{error.message}</ThemedText> : null}
        {isLoading ? <ActivityIndicator style={styles.loader} /> : null}

        {shops && shops.length === 0 && joining ? (
          <WaitingForInvitation email={user.email} onCheck={refresh} />
        ) : shops && shops.length === 0 ? (
          <View style={[styles.empty, { backgroundColor: theme.surface, borderColor: theme.border }]}>
            <View style={styles.emptyFront}>
              <Awning tone="card" />
              <View style={[styles.emptyDoor, { backgroundColor: theme.primaryMuted }]}>
                <Icon name="store" size={36} color="primary" />
              </View>
            </View>
            <ThemedText type="subtitle" style={styles.center}>
              Twój pierwszy sklep czeka na otwarcie
            </ThemedText>
            <ThemedText themeColor="textSecondary" style={[styles.center, styles.emptyText]}>
              Wybierz system, podaj nazwę, branżę i wygląd. Najpóźniej po dwóch minutach sklep będzie gotowy do dodawania produktów.
            </ThemedText>
            <Link href={user?.plan ? '/shops/new' : '/billing/checkout'} asChild>
              <Button
                title={user?.plan ? 'Załóż pierwszy sklep' : 'Wybierz plan i załóż sklep'}
                size="large"
                icon="plus"
              />
            </Link>
          </View>
        ) : (
          <View style={styles.grid}>
            {/* Suspended shops go last; the working ones come first. */}
            {[...(shops ?? [])]
              .sort((a, b) => Number(a.status === 'suspended') - Number(b.status === 'suspended'))
              .map((shop) => (
                <ShopSign key={shop.id} shop={shop} />
              ))}
          </View>
        )}

        {joining ? (
          shops?.length ? <OwnShopSwitch /> : null
        ) : (
          <Link href="/help" asChild>
            <Pressable
              accessibilityRole="link"
              style={StyleSheet.flatten([styles.tip, { backgroundColor: theme.accentMuted }])}>
              <Icon name="help" size={20} />
              <ThemedText style={styles.flex}>Pierwszy raz? Zobacz, jak dodać produkty i włączyć płatności.</ThemedText>
              <Icon name="chevron" size={18} color="textSecondary" />
            </Pressable>
          </Link>
        )}
      </Page>
    </SafeAreaView>
  );
}

/** For a team account without shops yet; the invitations above check for new ones meanwhile. */
function WaitingForInvitation({ email, onCheck }: { email: string; onCheck: () => Promise<void> }) {
  const theme = useTheme();
  const [checking, setChecking] = useState(false);

  async function check() {
    setChecking(true);
    // The invitation list above reads the same cache entry.
    await Promise.all([onCheck(), fetchQuery('/invitations/', () => api('/invitations/'), { force: true })]);
    setChecking(false);
  }

  return (
    <View style={[styles.empty, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <View style={styles.emptyFront}>
        <Awning tone="card" />
        <View style={[styles.emptyDoor, { backgroundColor: theme.primaryMuted }]}>
          <Icon name="mail" size={36} color="primary" />
        </View>
      </View>
      <ThemedText type="subtitle" style={styles.center}>
        Czekasz na zaproszenie
      </ThemedText>
      <ThemedText themeColor="textSecondary" style={[styles.center, styles.emptyText]}>
        Poproś właściciela sklepu, żeby zaprosił adres {email}. Zaproszenie pojawi się tutaj samo, a do tego przyjdzie
        e-mailem.
      </ThemedText>
      <Button title="Sprawdź teraz" variant="secondary" icon="refresh" onPress={check} loading={checking} />
      <OwnShopSwitch />
    </View>
  );
}

/** Turns a team account into one that opens its own shops; the plan comes next. */
function OwnShopSwitch() {
  const { updateProfile } = useAuth();
  const notify = useNotify();
  const [busy, setBusy] = useState(false);

  async function switchPurpose() {
    setBusy(true);
    try {
      await updateProfile({ purpose: 'own_shop' });
    } catch (e) {
      notify.error((e as Error).message);
      setBusy(false);
    }
  }

  return <Button title="Chcę założyć własny sklep" variant="ghost" onPress={switchPurpose} loading={busy} />;
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  center: {
    textAlign: 'center',
  },
  homeLink: {
    alignSelf: 'flex-start',
  },
  // The text takes the row while there is room; on narrow screens the button drops below it.
  headerText: {
    flexGrow: 1,
    flexBasis: 280,
  },
  header: {
    zIndex: 1,
    flexDirection: 'row',
    alignItems: 'flex-end',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
  loader: {
    marginVertical: Spacing.six,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
  empty: {
    alignItems: 'center',
    gap: Spacing.three,
    padding: Spacing.five,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  emptyFront: {
    width: 180,
    alignItems: 'center',
    marginBottom: Spacing.two,
  },
  emptyDoor: {
    width: 150,
    height: 90,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomLeftRadius: Radius.small,
    borderBottomRightRadius: Radius.small,
  },
  emptyText: {
    maxWidth: 420,
  },
  tip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
    padding: Spacing.three,
    borderRadius: Radius.medium,
  },
});
