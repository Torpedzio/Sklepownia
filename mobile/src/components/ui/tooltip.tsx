import { useEffect, useRef, useState, type ComponentRef, type ReactNode } from 'react';
import { Platform, Pressable, StyleSheet, useWindowDimensions, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

const BUBBLE_WIDTH = 260;
const ARROW_SIZE = 7;
// Touch screens have no hover, so a tap shows the bubble for a while instead.
const TOUCH_DURATION = 4000;

type Placement = { left: number; width: number; arrowLeft: number };

export type TooltipProps = {
  text: string;
  accessibilityLabel: string;
  /** Pick `above` only where the trigger has room over it; scroll views clip what sticks out. */
  side?: 'above' | 'below';
  children: ReactNode;
};

/** Shows `text` next to `children` on hover, keyboard focus or tap. */
export function Tooltip({ text, accessibilityLabel, side = 'below', children }: TooltipProps) {
  const theme = useTheme();
  const { width: windowWidth } = useWindowDimensions();
  const trigger = useRef<ComponentRef<typeof View>>(null);
  const [placement, setPlacement] = useState<Placement | null>(null);

  function show() {
    // Keep the bubble on screen even when the trigger sits at the edge.
    trigger.current?.measureInWindow((x, _y, width) => {
      const bubbleWidth = Math.min(BUBBLE_WIDTH, windowWidth - Spacing.three * 2);
      const centered = x + width / 2 - bubbleWidth / 2;
      const left = Math.max(Spacing.three, Math.min(centered, windowWidth - Spacing.three - bubbleWidth));
      setPlacement({ left: left - x, width: bubbleWidth, arrowLeft: x + width / 2 - left - ARROW_SIZE });
    });
  }

  const hide = () => setPlacement(null);

  useEffect(() => {
    if (!placement || Platform.OS === 'web') return;
    const timer = setTimeout(() => setPlacement(null), TOUCH_DURATION);
    return () => clearTimeout(timer);
  }, [placement]);

  return (
    <Pressable
      ref={trigger}
      accessibilityLabel={accessibilityLabel}
      accessibilityHint={text}
      onHoverIn={show}
      onHoverOut={hide}
      onFocus={show}
      onBlur={hide}
      onPress={Platform.OS === 'web' ? undefined : () => (placement ? hide() : show())}
      style={styles.trigger}>
      {children}
      {placement ? (
        <Animated.View
          entering={FadeIn.duration(120)}
          pointerEvents="none"
          style={[
            styles.bubble,
            side === 'above' ? styles.bubbleAbove : styles.bubbleBelow,
            { left: placement.left, width: placement.width, backgroundColor: theme.text },
          ]}>
          <ThemedText type="small" style={{ color: theme.background }}>
            {text}
          </ThemedText>
          <View
            style={[
              styles.arrow,
              side === 'above'
                ? [styles.arrowAbove, { borderTopColor: theme.text }]
                : [styles.arrowBelow, { borderBottomColor: theme.text }],
              { left: placement.arrowLeft },
            ]}
          />
        </Animated.View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  trigger: {
    alignSelf: 'flex-start',
  },
  bubble: {
    position: 'absolute',
    paddingVertical: Spacing.two,
    paddingHorizontal: Spacing.three,
    borderRadius: Radius.small,
    zIndex: 10,
  },
  bubbleAbove: {
    bottom: '100%',
    marginBottom: ARROW_SIZE + Spacing.one,
  },
  bubbleBelow: {
    top: '100%',
    marginTop: ARROW_SIZE + Spacing.one,
  },
  arrow: {
    position: 'absolute',
    width: 0,
    height: 0,
    borderLeftWidth: ARROW_SIZE,
    borderRightWidth: ARROW_SIZE,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
  },
  arrowAbove: {
    top: '100%',
    borderTopWidth: ARROW_SIZE,
  },
  arrowBelow: {
    bottom: '100%',
    borderBottomWidth: ARROW_SIZE,
  },
});
