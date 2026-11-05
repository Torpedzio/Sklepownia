import type { PropsWithChildren } from 'react';
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

type SettingsSectionProps = PropsWithChildren<{
  title: string;
  description?: string;
  /** The section has edits that aren't saved yet; shows the save bar. */
  dirty?: boolean;
  saving?: boolean;
  /** Another change is being saved in the shop, so this one has to wait. */
  waiting?: boolean;
  onSave?: () => void;
  onUndo?: () => void;
}>;

/** One card of the shop settings, saved on its own. */
export function SettingsSection({
  title,
  description,
  dirty,
  saving,
  waiting,
  onSave,
  onUndo,
  children,
}: SettingsSectionProps) {
  const theme = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: theme.surface, borderColor: dirty ? theme.primary : theme.border }]}>
      <View style={styles.header}>
        <ThemedText type="heading">{title}</ThemedText>
        {description ? (
          <ThemedText type="small" themeColor="textSecondary">
            {description}
          </ThemedText>
        ) : null}
      </View>
      <View style={styles.body}>{children}</View>
      {dirty && onSave ? (
        <View style={[styles.footer, { borderTopColor: theme.border }]}>
          {waiting ? (
            <ThemedText type="small" themeColor="textSecondary" style={styles.note}>
              Zapiszesz, gdy sklep skończy wprowadzać poprzednie zmiany.
            </ThemedText>
          ) : null}
          <View style={styles.buttons}>
            <Button title="Cofnij" variant="ghost" onPress={onUndo} disabled={saving} />
            <Button title="Zapisz" icon="check" onPress={onSave} loading={saving} disabled={waiting} />
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1.5,
  },
  header: {
    gap: Spacing.one,
  },
  body: {
    gap: Spacing.three,
  },
  footer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: Spacing.two,
    paddingTop: Spacing.three,
    borderTopWidth: 1,
  },
  note: {
    flexBasis: 240,
    flexGrow: 1,
  },
  buttons: {
    flexDirection: 'row',
    gap: Spacing.two,
  },
});
