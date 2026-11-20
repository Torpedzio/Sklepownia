import { Link, Stack, useLocalSearchParams } from 'expo-router';
import { useState, type ReactNode } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { Page } from '@/components/page';
import { Badge } from '@/components/status-badge';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Note } from '@/components/ui/note';
import { TextField } from '@/components/ui/text-field';
import { Radius, Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api, ApiError } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import { formatDate } from '@/lib/format';
import { plural } from '@/lib/plural';
import type { Person, ShopDetail, Team, TeamInvitation } from '@/lib/types';

/** The owner's team screen: inviting by e-mail, pending invitations and the people on the staff. */
export default function ShopTeamScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const theme = useTheme();
  const notify = useNotify();
  const { data: shop } = useApiQuery<ShopDetail>(`/shops/${id}/`);
  const { data: team, error, refresh } = useApiQuery<Team>(`/shops/${id}/team/`);
  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState<string>();
  const [sending, setSending] = useState(false);
  // The row whose button is working: `invitation:<id>`, `member:<id>` or `resend:<id>`.
  const [busyRow, setBusyRow] = useState<string>();

  const header = (
    <>
      <Stack.Screen
        options={{ title: 'Zespół', ...backArrowOptions({ pathname: '/shops/[id]', params: { id } }, 'Wróć do sklepu') }}
      />
      <View style={styles.header}>
        <ThemedText type="title">Zespół sklepu</ThemedText>
        {shop ? <ThemedText themeColor="textSecondary">{shop.name}</ThemedText> : null}
      </View>
    </>
  );

  if (!team) {
    return (
      <Page>
        {header}
        {error ? (
          <ThemedText themeColor="danger">{error.message}</ThemedText>
        ) : (
          <ActivityIndicator style={styles.loader} />
        )}
      </Page>
    );
  }

  const full = team.limit !== null && team.used >= team.limit;
  const pending = team.invitations.filter((invitation) => !invitation.expired).length;

  /** A new invitation, or the same address again with a fresh term. */
  async function invite(address: string, row?: string) {
    if (row) setBusyRow(row);
    else setSending(true);
    setEmailError(undefined);
    try {
      const invitation = await api<TeamInvitation>(`/shops/${id}/team/invitations/`, {
        method: 'POST',
        body: { email: address.trim() },
      });
      notify.success(`Zaproszenie wysłane na ${invitation.email}.`);
      if (!row) setEmail('');
      await refresh();
    } catch (e) {
      const fieldError = e instanceof ApiError ? e.fieldErrors.email : undefined;
      if (fieldError && !row) setEmailError(fieldError);
      else notify.error(fieldError ?? (e as Error).message);
    } finally {
      setSending(false);
      setBusyRow(undefined);
    }
  }

  async function remove(row: string, path: string, success: string) {
    setBusyRow(row);
    try {
      await api(path, { method: 'DELETE' });
      notify.success(success);
      await refresh();
    } catch (e) {
      notify.error((e as Error).message);
    } finally {
      setBusyRow(undefined);
    }
  }

  async function revoke(invitation: TeamInvitation) {
    const confirmed = await confirm(
      'Cofnąć zaproszenie?',
      `Link z wiadomości wysłanej na ${invitation.email} przestanie działać.`,
      'Cofnij zaproszenie',
    );
    if (confirmed) {
      await remove(
        `invitation:${invitation.id}`,
        `/shops/${id}/team/invitations/${invitation.id}/`,
        `Zaproszenie dla ${invitation.email} cofnięte.`,
      );
    }
  }

  async function removeMember(member: Person) {
    const who = member.name || member.email;
    const confirmed = await confirm(
      'Usunąć z zespołu?',
      `${who} przestanie widzieć sklep „${shop?.name ?? ''}” w aplikacji. Możesz zaprosić tę osobę ponownie.`,
      'Usuń z zespołu',
    );
    if (confirmed) {
      await remove(`member:${member.id}`, `/shops/${id}/team/members/${member.id}/`, `${who} nie jest już w zespole.`);
    }
  }

  const card = [styles.card, { backgroundColor: theme.surface, borderColor: theme.border }];

  return (
    <Page>
      {header}

      <View style={card}>
        <ThemedText type="heading">Zaproś osobę do obsługi</ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          Osoba z obsługi widzi sklep i jego sprzedaż. Ustawienia, kopie zapasowe, plan i usunięcie sklepu zostają przy
          Tobie. Zaproszenie przyjdzie e-mailem i jest ważne 7 dni. Każdy sklep ma własny zespół.
        </ThemedText>
        <TextField
          label="E-mail"
          value={email}
          onChangeText={(text) => {
            setEmail(text);
            setEmailError(undefined);
          }}
          error={emailError}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          textContentType="emailAddress"
          editable={!full}
          onSubmitEditing={() => email.trim() && !full && invite(email)}
        />
        <Button
          title="Wyślij zaproszenie"
          icon="mail"
          onPress={() => invite(email)}
          loading={sending}
          disabled={!email.trim() || full}
          style={styles.start}
        />
        <ThemedText type="small" themeColor="textSecondary">
          {team.limit === null
            ? 'Twój plan nie ogranicza liczby osób w zespole.'
            : `Zajęte ${team.used} z ${team.limit} miejsc w zespole, licząc wysłane zaproszenia.`}
        </ThemedText>
        {full ? (
          <View style={styles.fullNote}>
            <Note warning>
              {team.limit
                ? `Twój plan pozwala na ${team.limit} ${plural(team.limit, ['osobę', 'osoby', 'osób'])} z obsługi w tym sklepie. Usuń kogoś z zespołu, cofnij zaproszenie albo zmień plan.`
                : 'Bez planu nie zaprosisz nikogo do zespołu. Wybierz plan, a potem wróć tutaj.'}
            </Note>
            <Link href={team.limit ? '/billing/change' : '/billing/checkout'} asChild>
              <Button title={team.limit ? 'Zmień plan' : 'Wybierz plan'} variant="secondary" style={styles.start} />
            </Link>
          </View>
        ) : null}
      </View>

      <View style={card}>
        <ThemedText type="heading">W zespole</ThemedText>
        <PersonRow person={team.owner} label="Właściciel" />
        {team.members.map((member) => (
          <PersonRow
            key={member.id}
            person={member}
            note={`W zespole od ${formatDate(member.joined_at)}`}
            action={
              <Button
                title="Usuń"
                variant="ghost"
                onPress={() => removeMember(member)}
                loading={busyRow === `member:${member.id}`}
                disabled={busyRow !== undefined}
                accessibilityLabel={`Usuń ${member.name || member.email} z zespołu`}
              />
            }
          />
        ))}
        {team.members.length === 0 ? (
          <ThemedText type="small" themeColor="textSecondary">
            Na razie prowadzisz sklep sam. Osoby, które przyjmą zaproszenie, pojawią się tutaj.
          </ThemedText>
        ) : null}
      </View>

      {team.invitations.length ? (
        <View style={card}>
          <ThemedText type="heading">Zaproszenia</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            {pending
              ? `${pending} ${plural(pending, ['czeka', 'czekają', 'czeka'])} na odpowiedź.`
              : 'Żadne nie czeka na odpowiedź.'}{' '}
            Przyjęte i odrzucone znikają z listy.
          </ThemedText>
          {team.invitations.map((invitation) => (
            <PersonRow
              key={invitation.id}
              person={{ id: invitation.id, name: '', email: invitation.email }}
              note={invitation.expired ? undefined : `Ważne do ${formatDate(invitation.expires_at)}`}
              badge={invitation.expired ? <Badge label="Wygasło" color="warning" background="accentMuted" /> : null}
              action={
                <View style={styles.rowActions}>
                  <Button
                    title={invitation.expired ? 'Zaproś ponownie' : 'Wyślij ponownie'}
                    variant="secondary"
                    onPress={() => invite(invitation.email, `resend:${invitation.id}`)}
                    loading={busyRow === `resend:${invitation.id}`}
                    disabled={busyRow !== undefined}
                  />
                  <Button
                    title="Cofnij"
                    variant="ghost"
                    onPress={() => revoke(invitation)}
                    loading={busyRow === `invitation:${invitation.id}`}
                    disabled={busyRow !== undefined}
                    accessibilityLabel={`Cofnij zaproszenie dla ${invitation.email}`}
                  />
                </View>
              }
            />
          ))}
        </View>
      ) : null}
    </Page>
  );
}

type PersonRowProps = {
  person: Person;
  label?: string;
  note?: string;
  badge?: ReactNode;
  action?: ReactNode;
};

function PersonRow({ person, label, note, badge, action }: PersonRowProps) {
  const theme = useTheme();
  return (
    <View style={[styles.row, { borderTopColor: theme.border }]}>
      <View style={styles.rowText}>
        <ThemedText type="smallBold" numberOfLines={1}>
          {person.name || person.email}
        </ThemedText>
        {person.name ? (
          <ThemedText type="small" themeColor="textSecondary" numberOfLines={1}>
            {person.email}
          </ThemedText>
        ) : null}
        {note ? (
          <ThemedText type="small" themeColor="textSecondary">
            {note}
          </ThemedText>
        ) : null}
        {label ? <Badge label={label} color="primary" background="primaryMuted" /> : null}
        {badge}
      </View>
      {action}
    </View>
  );
}

const styles = StyleSheet.create({
  loader: {
    marginVertical: Spacing.six,
  },
  header: {
    gap: Spacing.two,
  },
  card: {
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  start: {
    alignSelf: 'flex-start',
  },
  fullNote: {
    gap: Spacing.two,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: Spacing.two,
    paddingTop: Spacing.three,
    borderTopWidth: 1,
  },
  rowText: {
    flexGrow: 1,
    flexBasis: 200,
    gap: Spacing.one,
  },
  rowActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
  },
});
