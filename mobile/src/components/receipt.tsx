import { StyleSheet, View } from 'react-native';
import Animated, { FadeIn, ZoomIn } from 'react-native-reanimated';

import { ThemedText } from '@/components/themed-text';
import { Fonts, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export type ReceiptRow = {
  label: string;
  value?: string;
  status?: 'done' | 'running' | 'pending' | 'failed';
  note?: string;
};

type ReceiptProps = {
  title: string;
  subtitle?: string;
  rows: ReceiptRow[];
  total?: { label: string; value: string };
  stamp?: { text: string; tone: 'success' | 'danger' };
  /** Print rows one by one, like a till. Used once, on the landing page. */
  animated?: boolean;
};

const MARKS = { done: '✓', running: '…', pending: '·', failed: '✕' };
const PRINT_DELAY = 140;

/** Progress shown as till receipt: the one place the app uses a typewriter face. */
export function Receipt({ title, subtitle, rows, total, stamp, animated = false }: ReceiptProps) {
  const theme = useTheme();
  const ink = { color: theme.receiptInk };
  const muted = { color: theme.receiptMuted };

  return (
    <View style={styles.wrapper}>
      <View style={[styles.paper, { backgroundColor: theme.receipt }]}>
        <ThemedText style={[styles.title, ink]}>{title}</ThemedText>
        {subtitle ? <ThemedText style={[styles.mono, styles.center, muted]}>{subtitle}</ThemedText> : null}
        <View style={[styles.rule, { borderColor: theme.receiptMuted }]} />

        {rows.map((row, index) => {
          const content = (
            <View style={styles.row}>
              <ThemedText
                style={[styles.mono, styles.mark, row.status === 'failed' ? { color: theme.danger } : row.status === 'pending' ? muted : ink]}>
                {MARKS[row.status ?? 'done']}
              </ThemedText>
              <View style={styles.label}>
                <ThemedText style={[styles.mono, row.status === 'pending' ? muted : ink]}>{row.label}</ThemedText>
                {row.note ? <ThemedText style={[styles.mono, { color: theme.danger }]}>{row.note}</ThemedText> : null}
              </View>
              {row.value ? <ThemedText style={[styles.mono, muted]}>{row.value}</ThemedText> : null}
            </View>
          );
          return animated ? (
            <Animated.View key={row.label} entering={FadeIn.delay(400 + index * PRINT_DELAY).duration(180)}>
              {content}
            </Animated.View>
          ) : (
            <View key={row.label}>{content}</View>
          );
        })}

        {total ? (
          <>
            <View style={[styles.rule, { borderColor: theme.receiptMuted }]} />
            <View style={styles.row}>
              <ThemedText style={[styles.monoBold, styles.label, ink]}>{total.label}</ThemedText>
              <ThemedText style={[styles.monoBold, ink]}>{total.value}</ThemedText>
            </View>
          </>
        ) : null}

        {stamp ? (
          <Animated.View
            entering={animated ? ZoomIn.delay(500 + rows.length * PRINT_DELAY).springify() : undefined}
            style={[styles.stamp, { borderColor: theme[stamp.tone] }]}>
            <ThemedText style={[styles.stampText, { color: theme[stamp.tone] }]}>{stamp.text}</ThemedText>
          </Animated.View>
        ) : null}
      </View>
      <TornEdge color={theme.receipt} />
    </View>
  );
}

function TornEdge({ color }: { color: string }) {
  return (
    <View style={styles.teeth}>
      {Array.from({ length: 48 }, (_, i) => (
        <View key={i} style={[styles.tooth, { borderTopColor: color }]} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    width: '100%',
  },
  paper: {
    paddingHorizontal: Spacing.four,
    paddingTop: Spacing.four,
    paddingBottom: Spacing.three,
    gap: Spacing.one,
    borderTopLeftRadius: 4,
    borderTopRightRadius: 4,
  },
  title: {
    fontFamily: Fonts.mono,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: '700',
    textAlign: 'center',
  },
  center: {
    textAlign: 'center',
  },
  mono: {
    fontFamily: Fonts.mono,
    fontSize: 13,
    lineHeight: 20,
  },
  monoBold: {
    fontFamily: Fonts.mono,
    fontSize: 14,
    lineHeight: 22,
    fontWeight: '700',
  },
  rule: {
    borderTopWidth: 1,
    borderStyle: 'dashed',
    marginVertical: Spacing.two,
  },
  row: {
    flexDirection: 'row',
    gap: Spacing.two,
  },
  mark: {
    width: 14,
    textAlign: 'center',
  },
  label: {
    flex: 1,
  },
  stamp: {
    position: 'absolute',
    right: Spacing.three,
    bottom: Spacing.four,
    borderWidth: 3,
    borderRadius: 8,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.one,
    transform: [{ rotate: '-12deg' }],
    opacity: 0.9,
  },
  stampText: {
    fontFamily: Fonts.display,
    fontSize: 26,
    lineHeight: 32,
    letterSpacing: 1,
  },
  teeth: {
    flexDirection: 'row',
    overflow: 'hidden',
    height: 8,
  },
  tooth: {
    width: 0,
    height: 0,
    borderLeftWidth: 6,
    borderRightWidth: 6,
    borderTopWidth: 8,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
  },
});
