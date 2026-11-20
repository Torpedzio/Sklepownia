import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { Icon } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import type { Invitation } from '@/lib/types';

const POLL_MS = 15_000;

/**
 * Invitations to other shops' staff; nothing while there are none. `onJoined` reloads the shop list; `poll` checks
 * for new ones while someone waits for an invitation.
 */
export function Invitations({ onJoined, poll = false }: { onJoined: () => void; poll?: boolean }) {
  const { data: invitations, refresh } = useApiQuery<Invitation[]>('/invitations/', {
    refetchInterval: () => (poll ? POLL_MS : false),
  });
  if (!invitations?.length) return null;
  return (
    <View style={styles.list}>
      {invitations.map((invitation) => (
        <InvitationCard key={invitation.id} invitation={invitation} onDone={refresh} onJoined={onJoined} />
      ))}
    </View>
  );
}

type CardProps = { invitation: Invitation; onDone: () => Promise<void>; onJoined: () => void };

function InvitationCard({ invitation, onDone, onJoined }: CardProps) {
  const theme = useTheme();
  const notify = useNotify();
  const [pending, setPending] = useState<'accept' | 'decline'>();
  const inviter = invitation.invited_by;
  const who = inviter ? inviter.name || inviter.email : 'Właściciel sklepu';

  async function answer(choice: 'accept' | 'decline') {
    setPending(choice);
    try {
      await api(`/invitations/${invitation.id}/${choice}/`, { method: 'POST' });
      if (choice === 'accept') {
        notify.success(`Dołączono do sklepu „${invitation.shop.name}”.`);
        onJoined();
      } else {
        notify.success('Zaproszenie odrzucone.');
      }
      await onDone();
    } catch (e) {
      notify.error((e as Error).message);
      setPending(undefined);
    }
  }

  return (
    <View style={[styles.card, { backgroundColor: theme.primaryMuted, borderColor: theme.primary }]}>
      <View style={styles.row}>
        <Icon name="mail" size={22} color="primary" />
        <View style={styles.text}>
          <ThemedText type="smallBold">Zaproszenie do obsługi sklepu</ThemedText>
          <ThemedText type="subtitle">{invitation.shop.name}</ThemedText>
          <ThemedText themeColor="textSecondary">
            {who} zaprasza Cię do zespołu. Zobaczysz sklep i jego sprzedaż. Ważne do{' '}
            {formatDate(invitation.expires_at)}.
          </ThemedText>
        </View>
      </View>
      <View style={styles.actions}>
        <Button
          title="Dołącz"
          icon="check"
          onPress={() => answer('accept')}
          loading={pending === 'accept'}
          disabled={pending !== undefined}
        />
        <Button
          title="Odrzuć"
          variant="ghost"
          onPress={() => answer('decline')}
          loading={pending === 'decline'}
          disabled={pending !== undefined}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  list: {
    gap: Spacing.three,
  },
  card: {
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1.5,
  },
  row: {
    flexDirection: 'row',
    gap: Spacing.three,
  },
  text: {
    flex: 1,
    gap: Spacing.one,
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
  },
});
