import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { TextField } from '@/components/ui/text-field';
import { Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useTheme } from '@/hooks/use-theme';
import { api, ApiError } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import { formatTime } from '@/lib/settings-form';
import type { OrderNote } from '@/lib/types';

/** The team's notes on an order, kept by the platform; the customer never sees them. */
export function OrderNotes({
  shopId,
  orderId,
  notes,
  onChange,
}: {
  shopId: string;
  orderId: string;
  notes: OrderNote[];
  onChange: (notes: OrderNote[]) => void;
}) {
  const theme = useTheme();
  const notify = useNotify();
  const [text, setText] = useState('');
  const [error, setError] = useState<string>();
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState<number>();
  const path = `/shops/${shopId}/orders/${orderId}/notes/`;

  async function add() {
    if (!text.trim()) {
      setError('Wpisz treść notatki.');
      return;
    }
    setAdding(true);
    setError(undefined);
    try {
      const note = await api<OrderNote>(path, { method: 'POST', body: { text } });
      setText('');
      onChange([...notes, note]);
    } catch (e) {
      const fieldError = e instanceof ApiError ? e.fieldErrors.text : undefined;
      if (fieldError) setError(fieldError);
      else notify.error((e as Error).message);
    } finally {
      setAdding(false);
    }
  }

  async function remove(note: OrderNote) {
    if (!(await confirm('Usunąć notatkę?', 'Zniknie dla całego zespołu.', 'Usuń notatkę'))) return;
    setDeleting(note.id);
    try {
      await api(`${path}${note.id}/`, { method: 'DELETE' });
      onChange(notes.filter((other) => other.id !== note.id));
    } catch (e) {
      notify.error((e as Error).message);
    } finally {
      setDeleting(undefined);
    }
  }

  return (
    <View style={styles.list}>
      {notes.length ? (
        notes.map((note) => (
          <View key={note.id} style={[styles.note, { borderTopColor: theme.border }]}>
            <ThemedText selectable>{note.text}</ThemedText>
            <View style={styles.meta}>
              <ThemedText type="small" themeColor="textSecondary" style={styles.flex}>
                {author(note)}, {formatTime(note.created_at)}
              </ThemedText>
              {note.can_delete ? (
                <Button
                  title="Usuń"
                  variant="ghost"
                  accessibilityLabel={`Usuń notatkę: ${note.text.slice(0, 40)}`}
                  loading={deleting === note.id}
                  onPress={() => remove(note)}
                />
              ) : null}
            </View>
          </View>
        ))
      ) : (
        <ThemedText type="small" themeColor="textSecondary">
          Zapisz tu, co zespół ma wiedzieć o zamówieniu. Klient tego nie widzi.
        </ThemedText>
      )}
      <TextField
        label="Nowa notatka"
        value={text}
        onChangeText={(value) => {
          setText(value);
          setError(undefined);
        }}
        error={error}
        multiline
        maxLength={2000}
      />
      <Button title="Dodaj notatkę" icon="plus" variant="secondary" loading={adding} onPress={add} style={styles.start} />
    </View>
  );
}

function author(note: OrderNote) {
  return note.author ? note.author.name || note.author.email : 'Konto usunięte';
}

const styles = StyleSheet.create({
  list: {
    gap: Spacing.three,
  },
  note: {
    gap: Spacing.one,
    paddingTop: Spacing.two,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  meta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  flex: {
    flex: 1,
  },
  start: {
    alignSelf: 'flex-start',
  },
});
