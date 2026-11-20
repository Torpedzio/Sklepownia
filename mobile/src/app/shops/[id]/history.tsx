import { Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, RefreshControl, StyleSheet, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { Page } from '@/components/page';
import { Badge } from '@/components/status-badge';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Brand } from '@/constants/brand';
import { Radius, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import type { ShopDetail, ShopEvent, ShopHistory } from '@/lib/types';

/** The owner's view of who did what in the shop and its team, newest first, grouped by day. */
export default function ShopHistoryScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const notify = useNotify();
  const { data: shop } = useApiQuery<ShopDetail>(`/shops/${id}/`);
  const { data: first, error, isRefreshing, refresh } = useApiQuery<ShopHistory>(`/shops/${id}/history/`);
  // Pages loaded with "Pokaż starsze", after the first one.
  const [older, setOlder] = useState<ShopHistory[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);

  const header = (
    <>
      <Stack.Screen
        options={{
          title: 'Historia',
          ...backArrowOptions({ pathname: '/shops/[id]', params: { id } }, 'Wróć do sklepu'),
        }}
      />
      <View style={styles.header}>
        <ThemedText type="title">Historia działań</ThemedText>
        <ThemedText themeColor="textSecondary">
          {shop ? `${shop.name}: kto` : 'Kto'} i kiedy zmienił coś w sklepie albo w jego zespole.
        </ThemedText>
      </View>
    </>
  );

  if (!first) {
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

  const pages = [first, ...older];
  const events = pages.flatMap((page) => page.events);
  const hasMore = pages[pages.length - 1].has_more;

  async function reload() {
    setOlder([]);
    await refresh();
  }

  async function loadMore() {
    setLoadingMore(true);
    try {
      const page = await api<ShopHistory>(`/shops/${id}/history/?before=${events[events.length - 1].id}`);
      setOlder((loaded) => [...loaded, page]);
    } catch (e) {
      notify.error((e as Error).message);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <Page refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={reload} />}>
      {header}
      {groupByDay(events).map(([day, dayEvents]) => (
        <View key={day} style={styles.day}>
          <ThemedText type="smallBold" themeColor="textSecondary">
            {dayLabel(dayEvents[0].created_at)}
          </ThemedText>
          <DayCard events={dayEvents} />
        </View>
      ))}
      {hasMore ? (
        <Button
          title="Pokaż starsze"
          variant="secondary"
          onPress={loadMore}
          loading={loadingMore}
          style={styles.start}
        />
      ) : null}
    </Page>
  );
}

function DayCard({ events }: { events: ShopEvent[] }) {
  const theme = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      {events.map((event, index) => (
        <EventRow key={event.id} event={event} first={index === 0} />
      ))}
    </View>
  );
}

function EventRow({ event, first }: { event: ShopEvent; first: boolean }) {
  const theme = useTheme();
  const { user } = useAuth();
  return (
    <View style={[styles.row, !first && { borderTopWidth: 1, borderTopColor: theme.border }]}>
      <ThemedText type="small" themeColor="textSecondary" style={styles.time}>
        {new Date(event.created_at).toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })}
      </ThemedText>
      <View style={styles.rowText}>
        <ThemedText type="smallBold">{event.title}</ThemedText>
        {event.detail ? (
          <ThemedText type="small" themeColor="textSecondary">
            {event.detail}
          </ThemedText>
        ) : null}
        <ThemedText type="small" themeColor="textSecondary">
          {actorLabel(event, user?.id)}
        </ThemedText>
        <StatusLine event={event} />
      </View>
    </View>
  );
}

function StatusLine({ event }: { event: ShopEvent }) {
  if (event.status === 'queued' || event.status === 'running') {
    return <Badge label="W trakcie" color="warning" background="accentMuted" />;
  }
  if (event.status !== 'failed') return null;
  return (
    <View style={styles.failed}>
      <Badge label="Nie udało się" color="danger" background="dangerMuted" />
      {event.error ? <ThemedText type="small">{event.error}</ThemedText> : null}
    </View>
  );
}

/** "Ty", "Ola Nowak (obsługa)", the platform or a deleted account. */
function actorLabel(event: ShopEvent, userId: number | undefined) {
  if (event.actor_role === 'system') return `${Brand.name}, automatycznie`;
  if (event.actor_role === 'deleted' || !event.actor) return 'Usunięte konto';
  if (event.actor.id === userId) return 'Ty';
  const name = event.actor.name || event.actor.email;
  return event.actor_role === 'staff' ? `${name} (obsługa)` : name;
}

function groupByDay(events: ShopEvent[]): [string, ShopEvent[]][] {
  const days = new Map<string, ShopEvent[]>();
  for (const event of events) {
    const day = new Date(event.created_at).toDateString();
    days.set(day, [...(days.get(day) ?? []), event]);
  }
  return [...days.entries()];
}

function dayLabel(iso: string, now = new Date()) {
  const date = new Date(iso);
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === now.toDateString()) return 'Dziś';
  if (date.toDateString() === yesterday.toDateString()) return 'Wczoraj';
  return formatDate(iso);
}

const styles = StyleSheet.create({
  loader: {
    marginVertical: Spacing.six,
  },
  header: {
    gap: Spacing.two,
  },
  day: {
    gap: Spacing.two,
  },
  card: {
    paddingHorizontal: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  row: {
    flexDirection: 'row',
    gap: Spacing.three,
    paddingVertical: Spacing.three,
  },
  time: {
    width: 44,
    fontVariant: ['tabular-nums'],
  },
  rowText: {
    flex: 1,
    gap: Spacing.half,
  },
  failed: {
    gap: Spacing.one,
    marginTop: Spacing.one,
  },
  start: {
    alignSelf: 'flex-start',
  },
});
