import { useEffect, useRef, useState, type PropsWithChildren } from 'react';
import { Pressable, ScrollView, StyleSheet, View, type ScrollViewInstance } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

import { Icon, type IconName } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { useReducedMotion } from '@/hooks/use-reduced-motion';
import { useTheme } from '@/hooks/use-theme';

export type SettingsMenuItem<K extends string> = {
  key: K;
  title: string;
  icon: IconName;
  dirty?: boolean;
};

type SettingsMenuProps<K extends string> = {
  items: SettingsMenuItem<K>[];
  active: K;
  onSelect: (key: K) => void;
  /** Wide screens: a list beside the content; narrow: a scrolling strip above it. */
  vertical: boolean;
};

const SWAP_OFFSET = 24;
const SWAP_MS = 260;

export function SettingsMenu<K extends string>({ items, active, onSelect, vertical }: SettingsMenuProps<K>) {
  const strip = useRef<ScrollViewInstance>(null);
  const positions = useRef(new Map<K, number>());
  const [measured, setMeasured] = useState(0);

  // Keep the chosen entry in view, also when the screen opens on a later section.
  useEffect(() => {
    const x = positions.current.get(active);
    if (!vertical && x !== undefined) strip.current?.scrollTo({ x: Math.max(0, x - Spacing.four), animated: true });
  }, [active, vertical, measured]);

  const entries = items.map((item) => (
    <MenuEntry
      key={item.key}
      item={item}
      selected={item.key === active}
      vertical={vertical}
      onPress={() => onSelect(item.key)}
      onX={(x) => {
        positions.current.set(item.key, x);
        setMeasured((count) => count + 1);
      }}
    />
  ));
  if (vertical) {
    return (
      <View style={styles.vertical} accessibilityRole="tablist">
        {entries}
      </View>
    );
  }
  return (
    <ScrollView
      ref={strip}
      horizontal
      showsHorizontalScrollIndicator={false}
      accessibilityRole="tablist"
      // Reaches the screen edges, so it's clear the strip scrolls.
      style={styles.strip}
      contentContainerStyle={styles.stripContent}>
      {entries}
    </ScrollView>
  );
}

function MenuEntry<K extends string>({
  item,
  selected,
  vertical,
  onPress,
  onX,
}: {
  item: SettingsMenuItem<K>;
  selected: boolean;
  vertical: boolean;
  onPress: () => void;
  onX: (x: number) => void;
}) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="tab"
      accessibilityState={{ selected }}
      accessibilityLabel={item.dirty ? `${item.title}, niezapisane zmiany` : item.title}
      onPress={onPress}
      onLayout={(event) => onX(event.nativeEvent.layout.x)}
      style={({ hovered, pressed }) => [
        vertical ? styles.row : styles.chip,
        {
          backgroundColor: selected
            ? theme.primaryMuted
            : hovered || pressed
              ? theme.surfaceMuted
              : vertical
                ? 'transparent'
                : theme.surface,
          borderColor: selected ? theme.primary : vertical ? 'transparent' : theme.border,
        },
      ]}>
      <Icon name={item.icon} size={18} color={selected ? 'primary' : 'textSecondary'} />
      <ThemedText
        type={selected ? 'smallBold' : 'small'}
        themeColor={selected ? 'primary' : 'text'}
        style={vertical && styles.label}
        numberOfLines={1}>
        {item.title}
      </ThemedText>
      {item.dirty ? <View style={[styles.dot, { backgroundColor: theme.accent }]} /> : null}
    </Pressable>
  );
}

type SettingsPaneProps<K extends string> = PropsWithChildren<{
  active: K;
  /** Menu order, for the direction a section comes from. */
  order: K[];
  /** As the menu: beside a list sections come from below or above, below a strip from the side. */
  vertical: boolean;
}>;

export function SettingsPane<K extends string>({ active, order, vertical, children }: SettingsPaneProps<K>) {
  const [shown, setShown] = useState(active);
  const [direction, setDirection] = useState(0);
  if (active !== shown) {
    setShown(active);
    setDirection(order.indexOf(active) > order.indexOf(shown) ? 1 : -1);
  }
  return (
    <SwapIn key={active} direction={direction} vertical={vertical}>
      {children}
    </SwapIn>
  );
}

function SwapIn({ direction, vertical, children }: PropsWithChildren<{ direction: number; vertical: boolean }>) {
  const reduceMotion = useReducedMotion();
  // The section the screen opens on appears as it is; only switching animates.
  const still = reduceMotion || direction === 0;
  const progress = useSharedValue(still ? 1 : 0);
  useEffect(() => {
    progress.set(withTiming(1, { duration: SWAP_MS }));
  }, [progress]);
  const style = useAnimatedStyle(() => {
    const offset = (1 - progress.get()) * SWAP_OFFSET * direction;
    return {
      opacity: progress.get(),
      transform: [vertical ? { translateY: offset } : { translateX: offset }],
    };
  });
  return <Animated.View style={[styles.pane, style]}>{children}</Animated.View>;
}

const styles = StyleSheet.create({
  vertical: {
    gap: Spacing.half,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two + Spacing.one,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two + Spacing.half,
    borderRadius: Radius.medium,
    borderWidth: 1.5,
  },
  label: {
    flex: 1,
  },
  strip: {
    marginHorizontal: -Spacing.four,
    flexGrow: 0,
  },
  stripContent: {
    gap: Spacing.two,
    paddingHorizontal: Spacing.four,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: Radius.pill,
    borderWidth: 1.5,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  pane: {
    gap: Spacing.three,
  },
});
