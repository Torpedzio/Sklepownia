import { createContext, use, useState, type PropsWithChildren, type ReactNode } from 'react';
import { Pressable, StyleSheet, View, type ScrollViewProps } from 'react-native';
import Animated, {
  FadeIn,
  FadeOut,
  runOnUI,
  scrollTo,
  useAnimatedReaction,
  useAnimatedRef,
  useAnimatedScrollHandler,
  useSharedValue,
  type AnimatedRef,
  type SharedValue,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { scheduleOnRN } from 'react-native-worklets';

import { Icon } from '@/components/icon';
import { KeyboardArea } from '@/components/keyboard-area';
import { MaxContentWidth, Spacing, WideBreakpoint } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { useWindowDimensions } from '@/hooks/use-window-dimensions';

type PageProps = PropsWithChildren<
  ScrollViewProps & {
    maxWidth?: number;
    /** Rendered full-width above the centered content (e.g. the awning and site header). */
    top?: ReactNode;
    /** Rendered full-width below the centered content (e.g. the footer). */
    bottom?: ReactNode;
  }
>;

/** The surrounding Page's scrolling, for sections that move with it. */
export type PageScroll = {
  scrollY: SharedValue<number>;
  /** For `scrollTo` from a worklet. */
  scrollRef: AnimatedRef<Animated.ScrollView>;
  /** True while a finger drags the page. */
  dragging: SharedValue<boolean>;
  /** Goes up by one every time the page comes to rest after a gesture. */
  rests: SharedValue<number>;
  /** True after a jump to the top until the next touch, so sections let the jump pass instead of stopping it. */
  jumping: SharedValue<boolean>;
};

// Below this release speed (per millisecond) the page stops where the finger let go.
const REST_VELOCITY = 0.05;

const PageScrollContext = createContext<PageScroll | null>(null);

/** Null outside a Page. */
export function usePageScroll() {
  return use(PageScrollContext);
}

export function Page({ children, maxWidth = MaxContentWidth, top, bottom, contentContainerStyle, ...rest }: PageProps) {
  const theme = useTheme();
  const scrollRef = useAnimatedRef<Animated.ScrollView>();
  const scrollY = useSharedValue(0);
  const dragging = useSharedValue(false);
  const rests = useSharedValue(0);
  const jumping = useSharedValue(false);
  const { width, height } = useWindowDimensions();
  const [showTopButton, setShowTopButton] = useState(false);

  // On narrow screens the button appears once the page is scrolled more than a screen down.
  useAnimatedReaction(
    () => width < WideBreakpoint && scrollY.get() > height,
    (show, previous) => {
      if (show !== previous) scheduleOnRN(setShowTopButton, show);
    },
  );

  function jumpToTop() {
    runOnUI(() => {
      jumping.set(true);
      scrollTo(scrollRef, 0, 0, false);
    })();
  }

  const onScroll = useAnimatedScrollHandler({
    onScroll: (event) => {
      scrollY.set(event.contentOffset.y);
    },
    onBeginDrag: () => {
      dragging.set(true);
      jumping.set(false);
    },
    onEndDrag: (event) => {
      dragging.set(false);
      // Without momentum no momentum events follow, so the page is already at rest.
      if (Math.abs(event.velocity?.y ?? 0) < REST_VELOCITY) rests.set(rests.get() + 1);
    },
    onMomentumEnd: () => {
      rests.set(rests.get() + 1);
    },
  });

  return (
    <PageScrollContext value={{ scrollY, scrollRef, dragging, rests, jumping }}>
      <KeyboardArea>
        <Animated.ScrollView
          ref={scrollRef}
          style={{ backgroundColor: theme.background }}
          contentContainerStyle={styles.scroll}
          contentInsetAdjustmentBehavior="automatic"
          keyboardShouldPersistTaps="handled"
          automaticallyAdjustKeyboardInsets
          onScroll={onScroll}
          scrollEventThrottle={16}
          {...rest}>
          {top}
          <View style={[styles.content, { maxWidth }, contentContainerStyle]}>{children}</View>
          {bottom}
        </Animated.ScrollView>
        {showTopButton ? <TopButton onPress={jumpToTop} /> : null}
      </KeyboardArea>
    </PageScrollContext>
  );
}

/** Jumps straight to the top of the page, past any sections that pin while scrolling. */
function TopButton({ onPress }: { onPress: () => void }) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <Animated.View
      entering={FadeIn.duration(160)}
      exiting={FadeOut.duration(160)}
      style={[styles.topButton, { bottom: insets.bottom + Spacing.three }]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Przewiń na górę strony"
        hitSlop={Spacing.two}
        onPress={onPress}
        style={({ pressed }) => [
          styles.topButtonFace,
          { backgroundColor: theme.primary, opacity: pressed ? 0.85 : 1 },
        ]}>
        <Icon name="arrowUp" size={22} tintColor={theme.onPrimary} />
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flexGrow: 1,
  },
  topButton: {
    position: 'absolute',
    right: Spacing.three,
  },
  topButtonFace: {
    width: 52,
    height: 52,
    borderRadius: 26,
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 3px 8px rgba(0, 0, 0, 0.18)',
  },
  content: {
    width: '100%',
    alignSelf: 'center',
    paddingHorizontal: Spacing.four,
    paddingVertical: Spacing.five,
    gap: Spacing.four,
    flexGrow: 1,
  },
});
