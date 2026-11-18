import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Fonts, Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { formatDay, formatMoney, formatShortDay } from '@/lib/format';
import { ordersLabel, scaleTop } from '@/lib/sales';
import type { SalesDay } from '@/lib/types';

const CHART_HEIGHT = 160;
const BAR_MAX_WIDTH = 24;

type Mode = 'chart' | 'table';

/** Daily revenue as thin bars, with the same numbers as a table one switch away. */
export function SalesChart({ days, currency }: { days: SalesDay[]; currency: string }) {
  const [view, setView] = useState<Mode>('chart');

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <ThemedText type="heading" style={styles.title}>
          Przychód dzień po dniu
        </ThemedText>
        <ViewSwitch value={view} onChange={setView} />
      </View>
      {view === 'chart' ? <Bars days={days} currency={currency} /> : <DayTable days={days} currency={currency} />}
    </View>
  );
}

function daySummary(day: SalesDay, currency: string) {
  return `${formatDay(day.date)}: ${formatMoney(day.revenue, currency)}, ${ordersLabel(day.orders)}`;
}

function Bars({ days, currency }: { days: SalesDay[]; currency: string }) {
  const theme = useTheme();
  const [selected, setSelected] = useState<number | null>(null);
  const top = scaleTop(Math.max(0, ...days.map((day) => Number(day.revenue))));
  const picked = selected === null ? undefined : days[selected];
  const leave = (index: number) => setSelected((current) => (current === index ? null : current));

  return (
    <View style={styles.chart}>
      {/* The readout keeps its height, so the bars don't jump when it changes. */}
      <ThemedText type={picked ? 'smallBold' : 'small'} themeColor={picked ? 'text' : 'textSecondary'}>
        {picked
          ? daySummary(picked, currency)
          : top
            ? 'Wskaż słupek, żeby zobaczyć dzień.'
            : 'W ostatnich 30 dniach nie było sprzedaży.'}
      </ThemedText>

      <View style={styles.plot}>
        {top ? (
          <View style={[styles.gridline, { borderColor: theme.border }]}>
            <ThemedText
              type="small"
              themeColor="textSecondary"
              style={[styles.scale, { backgroundColor: theme.surface }]}>
              {formatMoney(top, currency, { whole: true })}
            </ThemedText>
          </View>
        ) : null}
        <View style={[styles.bars, { borderColor: theme.textSecondary }]}>
          {days.map((day, index) => {
            const share = top ? Number(day.revenue) / top : 0;
            return (
              // The whole column answers, so a thin bar is easy to hit.
              <Pressable
                key={day.date}
                accessibilityRole="button"
                accessibilityLabel={daySummary(day, currency)}
                onPressIn={() => setSelected(index)}
                onHoverIn={() => setSelected(index)}
                onHoverOut={() => leave(index)}
                onFocus={() => setSelected(index)}
                onBlur={() => leave(index)}
                style={styles.column}>
                {share > 0 ? (
                  <View
                    style={[
                      styles.bar,
                      {
                        // At least a sliver, so a small day still shows.
                        height: Math.max(2, share * CHART_HEIGHT),
                        backgroundColor: theme.chart,
                        opacity: selected === null || selected === index ? 1 : 0.4,
                      },
                    ]}
                  />
                ) : null}
              </Pressable>
            );
          })}
        </View>
      </View>

      <View style={styles.axis}>
        <ThemedText type="small" themeColor="textSecondary">
          {days.length ? formatShortDay(days[0].date) : ''}
        </ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          dziś
        </ThemedText>
      </View>
    </View>
  );
}

function DayTable({ days, currency }: { days: SalesDay[]; currency: string }) {
  const theme = useTheme();
  return (
    <View style={styles.table}>
      <View style={[styles.row, { borderColor: theme.border }]}>
        <ThemedText type="smallBold" themeColor="textSecondary" style={styles.dayCell}>
          Dzień
        </ThemedText>
        <ThemedText type="smallBold" themeColor="textSecondary" style={styles.numberCell}>
          Zamówienia
        </ThemedText>
        <ThemedText type="smallBold" themeColor="textSecondary" style={styles.numberCell}>
          Przychód
        </ThemedText>
      </View>
      {/* Newest first, like the list of orders. */}
      {[...days].reverse().map((day) => (
        <View key={day.date} style={[styles.row, { borderColor: theme.border }]}>
          <ThemedText type="small" style={styles.dayCell}>
            {formatDay(day.date)}
          </ThemedText>
          <ThemedText type="small" style={[styles.numberCell, styles.digits]}>
            {day.orders}
          </ThemedText>
          <ThemedText type="small" style={[styles.numberCell, styles.digits]}>
            {formatMoney(day.revenue, currency)}
          </ThemedText>
        </View>
      ))}
    </View>
  );
}

function ViewSwitch({ value, onChange }: { value: Mode; onChange: (value: Mode) => void }) {
  const theme = useTheme();
  const options: { value: Mode; label: string }[] = [
    { value: 'chart', label: 'Wykres' },
    { value: 'table', label: 'Tabela' },
  ];
  return (
    <View accessibilityRole="radiogroup" style={[styles.switch, { backgroundColor: theme.surfaceMuted }]}>
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <Pressable
            key={option.value}
            accessibilityRole="radio"
            accessibilityState={{ selected }}
            onPress={() => onChange(option.value)}
            style={[styles.switchOption, selected && { backgroundColor: theme.surface, borderColor: theme.border }]}>
            <ThemedText type={selected ? 'smallBold' : 'small'} themeColor={selected ? 'text' : 'textSecondary'}>
              {option.label}
            </ThemedText>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: Spacing.three,
  },
  header: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: Spacing.two,
  },
  title: {
    flex: 1,
    minWidth: 180,
  },
  chart: {
    gap: Spacing.two,
  },
  plot: {
    height: CHART_HEIGHT,
    justifyContent: 'flex-end',
  },
  gridline: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderStyle: 'dashed',
  },
  scale: {
    position: 'absolute',
    top: -10,
    left: 0,
    paddingRight: Spacing.one,
    fontSize: 12,
    lineHeight: 18,
  },
  bars: {
    height: CHART_HEIGHT,
    flexDirection: 'row',
    alignItems: 'flex-end',
    borderBottomWidth: 1,
  },
  column: {
    flex: 1,
    height: '100%',
    justifyContent: 'flex-end',
    alignItems: 'center',
    // Two pixels of surface between neighbours.
    paddingHorizontal: 1,
  },
  bar: {
    width: '100%',
    maxWidth: BAR_MAX_WIDTH,
    borderTopLeftRadius: 4,
    borderTopRightRadius: 4,
  },
  axis: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  table: {
    gap: 0,
  },
  row: {
    flexDirection: 'row',
    gap: Spacing.two,
    paddingVertical: Spacing.two,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  dayCell: {
    flex: 2,
  },
  numberCell: {
    flex: 1,
    textAlign: 'right',
  },
  digits: {
    fontFamily: Fonts.bodyMedium,
    fontVariant: ['tabular-nums'],
  },
  switch: {
    flexDirection: 'row',
    padding: Spacing.half,
    borderRadius: Radius.pill,
  },
  switchOption: {
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.one,
    borderRadius: Radius.pill,
    borderWidth: 1,
    borderColor: 'transparent',
  },
});
