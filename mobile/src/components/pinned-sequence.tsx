import { useState, type ReactNode } from 'react';
import { Platform, StyleSheet, useWindowDimensions, View, type ViewStyle } from 'react-native';
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

// Scrolling this far inside the section moves on to the next item.
const STEP = 500;
// The switch happens this early into a step, so about one turn of a mouse wheel is enough.
const SWITCH_AT = 0.25;
// How far an item travels as it jumps in, and how long it takes.
const ENTER_OFFSET = 80;
const ENTER_MS = 420;
const HEADER_GAP = Spacing.four;
// Used until the header has been measured.
const HEADER_ESTIMATE = 120;

type PinnedSequenceProps = {
  header: ReactNode;
  count: number;
  page: PageScroll;
  /** Height of the stage, given the room left on the screen below the pinned header. */
  stageHeight: (room: number) => number;
  /** The stage, given the index of the item to show and the stage height. */
  children: (active: number, height: number) => ReactNode;
};

/**
 * A section that pins its header and stage to the top of the screen while the page scrolls through it,
 * swapping the stage to the next item every short scroll; after the last item the section scrolls away.
 *
 * The web pins with CSS `sticky`, which the browser keeps exactly in place. Native has no sticky views,
 * so there the section is moved by exactly the scroll offset, from a position measured before it pinned.
 * On native one swipe also moves by one item at most: the page stops on the next item even when the
 * swipe's momentum would carry further, and settles on the shown item when it comes to rest.
 */
export function PinnedSequence({ header, count, page, stageHeight, children }: PinnedSequenceProps) {
  const { height: windowHeight } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const [headerHeight, setHeaderHeight] = useState(HEADER_ESTIMATE);
  const [active, setActive] = useState(0);

  // Where the section pins: just below the top edge of the screen.
  const pinTop = insets.top + Spacing.four;
  const height = stageHeight(windowHeight - pinTop - headerHeight - HEADER_GAP - Spacing.four);
  const distance = STEP * (count - 1);
  const native = Platform.OS !== 'web';
  const { scrollY, scrollRef, dragging, rests, jumping } = page;

  const section = useAnimatedRef<Animated.View>();
  // Top of the section in screen coordinates with the page scrolled to 0; -1 until measured.
  const anchor = useSharedValue(-1);
  // How far the page has scrolled past the pinning point; below 0 before the section, above `distance` after it.
  const travel = useSharedValue(0);
  const shown = useSharedValue(0);
  // Positions one swipe may reach: -1 is "before the section", `count` is "after it".
  const lowest = useSharedValue(-1);
  const highest = useSharedValue(count);
  // Scroll position the page is being moved to, so the same stop isn't requested every frame.
  const stoppingAt = useSharedValue(-1);

  useAnimatedReaction(
    () => scrollY.get(),
    (scroll) => {
      let top = anchor.get();
      const pinned = top >= 0 && pinTop - (top - scroll) > 0 && pinTop - (top - scroll) < distance;
      // Measured only while not pinned: a measurement can lag a frame behind the scroll, which would make
      // the pinned stage shake. While pinned the stage moves by the scroll offset alone.
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

  // A new swipe may go one item either way from where it started.
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

  // Coming to rest between two items, the page settles on the one on the stage.
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

/**
 * One item on a PinnedSequence stage. All items stay mounted on top of each other; the active one
 * fades in from the direction of the scroll and the others fade out the opposite way.
 */
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

/** Title and lead of a home page section. */
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
