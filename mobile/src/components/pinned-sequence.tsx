import { useState, type ReactNode } from 'react';
import { Platform, StyleSheet, View, type ViewStyle } from 'react-native';
import Animated, {
  measure,
  scrollTo,
  useAnimatedReaction,
  useAnimatedRef,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { scheduleOnRN } from 'react-native-worklets';

import type { PageScroll } from '@/components/page';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { useWindowDimensions } from '@/hooks/use-window-dimensions';

// Scroll distance per item.
const STEP = 500;
// Switch a quarter into a step: about one turn of a mouse wheel.
const SWITCH_AT = 0.25;
const ENTER_OFFSET = 80;
const ENTER_MS = 420;
const HEADER_GAP = Spacing.four;
const HEADER_ESTIMATE = 120;

type PinnedSequenceProps = {
  header: ReactNode;
  count: number;
  page: PageScroll;
  /** `room`: screen height left below the pinned header. */
  stageHeight: (room: number) => number;
  children: (active: number, height: number) => ReactNode;
};

/**
 * Pins its header and stage while the page scrolls through, showing the next item every short scroll. Web uses
 * CSS `sticky`; native (no sticky views) offsets the section by the scroll and limits a swipe to one item.
 */
export function PinnedSequence({ header, count, page, stageHeight, children }: PinnedSequenceProps) {
  const { height: windowHeight } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const [headerHeight, setHeaderHeight] = useState(HEADER_ESTIMATE);
  const [active, setActive] = useState(0);

  const pinTop = insets.top + Spacing.four;
  const height = stageHeight(windowHeight - pinTop - headerHeight - HEADER_GAP - Spacing.four);
  const distance = STEP * (count - 1);
  const native = Platform.OS !== 'web';
  const { scrollY, scrollRef, dragging, rests, jumping } = page;

  const section = useAnimatedRef<Animated.View>();
  // Section top in screen coordinates at scroll 0; -1 until measured.
  const anchor = useSharedValue(-1);
  // Scroll past the pinning point: below 0 before the section, above `distance` after it.
  const travel = useSharedValue(0);
  const shown = useSharedValue(0);
  // Positions one swipe may reach: -1 is before the section, `count` after it.
  const lowest = useSharedValue(-1);
  const highest = useSharedValue(count);
  // Target scroll offset, so the same stop isn't requested every frame.
  const stoppingAt = useSharedValue(-1);

  useAnimatedReaction(
    () => scrollY.get(),
    (scroll) => {
      let top = anchor.get();
      const pinned = top >= 0 && pinTop - (top - scroll) > 0 && pinTop - (top - scroll) < distance;
      // Measured only while not pinned: a measurement can lag a frame behind the scroll and shake the stage.
      if (!pinned) {
        const box = measure(section);
        if (box) {
          top = box.pageY + scroll;
          anchor.set(top);
        }
      }
      if (top < 0) return;

      const raw = pinTop - (top - scroll);
      travel.set(raw);
      const position = raw < 0 ? -1 : raw > distance ? count : Math.floor(raw / STEP + 1 - SWITCH_AT);
      let reached = Math.min(Math.max(position, -1), count);
      if (native && !jumping.get() && (reached < lowest.get() || reached > highest.get())) {
        reached = Math.min(Math.max(reached, lowest.get()), highest.get());
        const target = top - pinTop + Math.min(Math.max(reached, 0), count - 1) * STEP;
        if (!dragging.get() && stoppingAt.get() !== target) {
          stoppingAt.set(target);
          scrollTo(scrollRef, 0, target, true);
        }
      }
      const index = Math.min(Math.max(reached, 0), count - 1);
      if (index !== shown.get()) {
        shown.set(index);
        scheduleOnRN(setActive, index);
      }
    },
  );

  useAnimatedReaction(
    () => dragging.get(),
    (isDragging, wasDragging) => {
      if (!native || !isDragging || wasDragging) return;
      stoppingAt.set(-1);
      const raw = travel.get();
      const from = raw < 0 ? -1 : raw > distance ? count : shown.get();
      lowest.set(from - 1);
      highest.set(from + 1);
    },
  );

  // Coming to rest between two items, settle on the one on the stage.
  useAnimatedReaction(
    () => rests.get(),
    (restCount, previous) => {
      if (!native || previous === null || restCount === previous) return;
      stoppingAt.set(-1);
      const raw = travel.get();
      if (raw <= 0 || raw >= distance) return;
      const target = anchor.get() - pinTop + shown.get() * STEP;
      if (Math.abs(scrollY.get() - target) > 1) scrollTo(scrollRef, 0, target, true);
    },
  );

  const followScroll = useAnimatedStyle(() => ({
    transform: [{ translateY: native ? Math.min(Math.max(travel.get(), 0), distance) : 0 }],
  }));
  const pin = native ? followScroll : ({ position: 'sticky', top: pinTop } as unknown as ViewStyle);

  return (
    <Animated.View ref={section} style={{ height: headerHeight + HEADER_GAP + height + distance }}>
      <Animated.View style={pin}>
        <View onLayout={(event) => setHeaderHeight(Math.ceil(event.nativeEvent.layout.height))}>{header}</View>
        <View style={[styles.stage, { height }]}>{children(active, height)}</View>
      </Animated.View>
    </Animated.View>
  );
}

type SwapLayerProps = { index: number; active: number; children: ReactNode };

/** All items stay mounted, stacked; the active one fades in from the scroll direction, the rest fade out. */
export function SwapLayer({ index, active, children }: SwapLayerProps) {
  const theme = useTheme();
  const offset = index === active ? 0 : index > active ? ENTER_OFFSET : -ENTER_OFFSET;
  const swap = useAnimatedStyle(
    () => ({
      opacity: withTiming(index === active ? 1 : 0, { duration: ENTER_MS }),
      transform: [{ translateY: withTiming(offset, { duration: ENTER_MS }) }],
    }),
    [index, active, offset],
  );
  return (
    <Animated.View
      pointerEvents={index === active ? 'auto' : 'none'}
      aria-hidden={index !== active}
      style={[styles.layer, { backgroundColor: theme.background }, swap]}>
      {children}
    </Animated.View>
  );
}

export function SectionHeader({ title, text }: { title: string; text?: string }) {
  return (
    <View style={styles.header}>
      <ThemedText type="title">{title}</ThemedText>
      {text ? (
        <ThemedText type="lead" themeColor="textSecondary">
          {text}
        </ThemedText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stage: {
    marginTop: HEADER_GAP,
  },
  layer: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },
  header: {
    gap: Spacing.two,
    maxWidth: 640,
  },
});
