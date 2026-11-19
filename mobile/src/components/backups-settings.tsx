import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Note } from '@/components/ui/note';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { formatSize } from '@/lib/format';
import { plural } from '@/lib/plural';
import type { ShopBackup, ShopBackups } from '@/lib/types';

type Props = {
  backups: ShopBackups | undefined;
  /** Another job runs in the shop, so this waits. */
  busy: boolean;
  /** A backup or restore request is on its way. */
  starting: boolean;
  onBackup: () => void;
  onRestore: (backup: ShopBackup) => void;
};

const DAY_MS = 86_400_000;

function moment(iso: string, now: Date) {
  const date = new Date(iso);
  const time = date.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
  const day = date.toDateString();
  const relative =
    day === now.toDateString()
      ? 'today'
      : day === new Date(now.getTime() - DAY_MS).toDateString()
        ? 'yesterday'
        : day === new Date(now.getTime() + DAY_MS).toDateString()
          ? 'tomorrow'
          : null;
  return { relative, time, date: date.toLocaleDateString('pl-PL', { day: 'numeric', month: 'long' }) };
}

/** "Dziś, 03:00", "Wczoraj, 15:20", "16 listopada, 03:00": a backup in the list. */
export function backupTime(iso: string, now = new Date()) {
  const { relative, time, date } = moment(iso, now);
  return `${relative === 'today' ? 'Dziś' : relative === 'yesterday' ? 'Wczoraj' : date}, ${time}`;
}

/** "dzisiejszą kopię z 03:00", "kopię z 16 listopada, 03:00": what is restored, for "Przywrócić …?". */
export function backupName(iso: string, now = new Date()) {
  const { relative, time, date } = moment(iso, now);
  if (relative === 'today') return `dzisiejszą kopię z ${time}`;
  if (relative === 'yesterday') return `wczorajszą kopię z ${time}`;
  return `kopię z ${date}, ${time}`;
}

/** "dziś o 03:00", "jutro o 03:00": the next nightly backup. */
function nextTime(iso: string, now = new Date()) {
  const { relative, time, date } = moment(iso, now);
  return `${relative === 'today' ? 'dziś' : relative === 'tomorrow' ? 'jutro' : date} o ${time}`;
}

/** "Co noc… Zostaje najnowsza kopia z każdego z ostatnich 7 dni i 4 tygodni." */
export function backupsDescription(backups: ShopBackups | undefined) {
  const intro = 'Co noc zapisujemy pliki, produkty, zamówienia i ustawienia sklepu.';
  if (!backups) return intro;
  const days = `${backups.keep_daily} ${plural(backups.keep_daily, ['dnia', 'dni', 'dni'])}`;
  const weeks = `${backups.keep_weekly} ${plural(backups.keep_weekly, ['tygodnia', 'tygodni', 'tygodni'])}`;
  return `${intro} Zostaje najnowsza kopia z każdego z ostatnich ${days} i ${weeks}.`;
}

export function BackupsSettings({ backups, busy, starting, onBackup, onRestore }: Props) {
  const theme = useTheme();
  if (!backups) {
    return (
      <ThemedText type="small" themeColor="textSecondary">
        Wczytujemy kopie…
      </ThemedText>
    );
  }
  if (!backups.enabled) {
    return <Note warning>Kopie zapasowe są chwilowo wyłączone. Sklep działa jak zwykle.</Note>;
  }
  const left = backups.manual_left;
  return (
    <>
      <View style={styles.row}>
        <View style={styles.text}>
          <ThemedText type="smallBold">Kopia teraz</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            {left
              ? `Przyda się przed większymi zmianami w panelu sklepu. Dziś możesz zrobić jeszcze ${left}.`
              : 'Na dziś to już wszystkie kopie, które możesz zrobić sam. W nocy powstanie kopia nocna.'}
          </ThemedText>
        </View>
        <Button
          title="Zrób kopię"
          icon="backup"
          variant="secondary"
          disabled={busy || starting || !left}
          onPress={onBackup}
        />
      </View>
      {backups.backups.length ? (
        <View accessibilityRole="list" style={styles.list}>
          {backups.backups.map((backup) => (
            <View key={backup.id} style={[styles.item, styles.divider, { borderTopColor: theme.border }]}>
              <View style={styles.itemText}>
                <ThemedText type="smallBold">{backupTime(backup.created_at)}</ThemedText>
                <ThemedText type="small" themeColor="textSecondary">
                  {backup.size ? `${backup.kind_display}, ${formatSize(backup.size)}` : backup.kind_display}
                </ThemedText>
              </View>
              <Button
                title="Przywróć"
                variant="ghost"
                accessibilityLabel={`Przywróć ${backupName(backup.created_at)}`}
                disabled={busy || starting}
                onPress={() => onRestore(backup)}
              />
            </View>
          ))}
        </View>
      ) : (
        <ThemedText type="small" themeColor="textSecondary">
          Kopii jeszcze nie ma. Pierwsza powstanie {nextTime(backups.nightly_at)}.
        </ThemedText>
      )}
    </>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: Spacing.three,
  },
  list: {
    gap: Spacing.three,
  },
  // Side by side on phones too: the list is short to scan.
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  itemText: {
    flex: 1,
    gap: Spacing.half,
  },
  divider: {
    borderTopWidth: 1,
    paddingTop: Spacing.three,
  },
  text: {
    flexBasis: 220,
    flexGrow: 1,
    gap: Spacing.half,
  },
});
