import { router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import { plural } from '@/lib/plural';
import type { ShopDetail, Team } from '@/lib/types';

/** For the owner: who runs the shop with them, and the way to the team screen. */
export function TeamCard({ shopId }: { shopId: number }) {
  const theme = useTheme();
  const { data: team } = useApiQuery<Team>(`/shops/${shopId}/team/`);
  const members = team?.members.length ?? 0;
  const pending = team?.invitations.filter((invitation) => !invitation.expired).length ?? 0;

  let summary = 'Zaproś osoby, które pomogą Ci prowadzić sklep. Zobaczą go w aplikacji razem ze sprzedażą.';
  if (members || pending) {
    summary = [
      members ? `${members} ${plural(members, ['osoba', 'osoby', 'osób'])} z obsługi` : 'Nikt jeszcze nie dołączył',
      pending ? `${pending} ${plural(pending, ['zaproszenie czeka', 'zaproszenia czekają', 'zaproszeń czeka'])}` : '',
    ]
      .filter(Boolean)
      .join(', ');
    summary += '.';
  }

  return (
    <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <ThemedText type="heading">Zespół sklepu</ThemedText>
      {team ? (
        <ThemedText type="small" themeColor="textSecondary">
          {summary}
        </ThemedText>
      ) : null}
      <Button
        title={members || pending ? 'Zarządzaj zespołem' : 'Zaproś do zespołu'}
        icon="person"
        variant="secondary"
        style={styles.start}
        onPress={() => router.push({ pathname: '/shops/[id]/team', params: { id: String(shopId) } })}
      />
    </View>
  );
}

/** For the staff: whose shop it is, and leaving its team. */
export function LeaveTeam({ shop }: { shop: Pick<ShopDetail, 'id' | 'name' | 'owner'> }) {
  const theme = useTheme();
  const notify = useNotify();
  const [busy, setBusy] = useState(false);
  const owner = shop.owner.name ? `${shop.owner.name} (${shop.owner.email})` : shop.owner.email;

  async function leave() {
    const confirmed = await confirm(
      'Opuścić zespół?',
      `Sklep „${shop.name}” zniknie z Twojej listy. Wrócisz do zespołu tylko z nowym zaproszeniem.`,
      'Opuść zespół',
    );
    if (!confirmed) return;
    setBusy(true);
    try {
      await api(`/shops/${shop.id}/leave/`, { method: 'POST' });
      notify.success(`Nie jesteś już w zespole sklepu „${shop.name}”.`);
      router.replace('/shops');
    } catch (e) {
      notify.error((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <ThemedText type="heading">Obsługujesz ten sklep</ThemedText>
      <ThemedText type="small" themeColor="textSecondary">
        Sklep należy do: {owner}. Właściciel zaprosił Cię do zespołu i może Cię z niego usunąć.
      </ThemedText>
      <Button title="Opuść zespół" variant="ghost" icon="logout" onPress={leave} loading={busy} style={styles.start} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: Spacing.two,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  start: {
    alignSelf: 'flex-start',
  },
});
