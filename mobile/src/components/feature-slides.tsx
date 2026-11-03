import { useEffect, useMemo, useRef, useState, type ComponentRef } from 'react';
import {
  Image,
  PanResponder,
  Platform,
  Pressable,
  StyleSheet,
  useWindowDimensions,
  View,
  type LayoutChangeEvent,
} from 'react-native';
import Animated, {
  FadeInLeft,
  FadeInRight,
  useAnimatedStyle,
  useReducedMotion,
  withTiming,
} from 'react-native-reanimated';

import { Awning } from '@/components/awning';
import { Icon, type IconName } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import type { Feature } from '@/constants/content';
import { Radius, Spacing, WideBreakpoint } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

const AUTOPLAY_MS = 7000;
const SWIPE_DISTANCE = 50;
const AWNING_HEIGHT = 22;
// On narrow screens the card sits under the picture instead of on it, overlapping by this much.
const NARROW_PICTURE_HEIGHT = 340;
const CARD_OVERLAP = 48;

/**
 * Features as a full-width shop window: one slide per feature under the awning, with a photo
 * or a drawn backdrop and a card describing it. Advances on its own until hovered or paused.
 */
export function FeatureSlides({ features }: { features: Feature[] }) {
  const theme = useTheme();
  const { width: windowWidth, height } = useWindowDimensions();
  const column = useRef<ComponentRef<typeof View>>(null);
  // The slides break out of the centered page column to the page edges. On the web the page is
  // narrower than the window by its scrollbar, so the column's position is measured there.
  const [columnBox, setColumnBox] = useState<{ left: number; width: number }>();
  const inset = columnBox?.left ?? Spacing.four;
  const width = columnBox ? columnBox.width + inset * 2 : windowWidth;
  const wide = width >= WideBreakpoint;
  const reduceMotion = useReducedMotion();
  const [index, setIndex] = useState(0);
  const [direction, setDirection] = useState<1 | -1>(1);
  const [paused, setPaused] = useState(false);
  const [hovered, setHovered] = useState(false);
  const count = features.length;
  const feature = features[index];
  const playing = !paused && !hovered && !reduceMotion;

  useEffect(() => {
    if (!playing) return;
    const timer = setTimeout(() => {
      setDirection(1);
      setIndex((i) => (i + 1) % count);
    }, AUTOPLAY_MS);
    return () => clearTimeout(timer);
  }, [index, playing, count]);

  function measureColumn(event: LayoutChangeEvent) {
    const columnWidth = event.nativeEvent.layout.width;
    if (Platform.OS === 'web') {
      column.current?.measureInWindow((left) => setColumnBox({ left, width: columnWidth }));
    } else {
      setColumnBox({ left: (windowWidth - columnWidth) / 2, width: columnWidth });
    }
  }

  function go(to: number) {
    setDirection(to >= index ? 1 : -1);
    setIndex((to + count) % count);
  }

  const swipe = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dx) > 12 && Math.abs(g.dx) > Math.abs(g.dy) * 1.5,
        onPanResponderRelease: (_, g) => {
          if (Math.abs(g.dx) < SWIPE_DISTANCE) return;
          const step = g.dx < 0 ? 1 : -1;
          setDirection(step);
          setIndex((i) => (i + step + count) % count);
        },
      }),
    [count],
  );

  const pictureHeight = wide ? Math.round(Math.min(Math.max(height * 0.72, 500), 680)) : NARROW_PICTURE_HEIGHT;
  // Drawn slides take turns through these backgrounds.
  const drawnTones = [theme.primary, '#14213D', theme.primaryMuted];
  const drawnTone = (i: number) =>
    drawnTones[features.slice(0, i).filter((item) => !item.image).length % drawnTones.length];

  return (
    <View ref={column} onLayout={measureColumn}>
      <Pressable
        accessible={false}
        focusable={false}
        onHoverIn={() => setHovered(true)}
        onHoverOut={() => setHovered(false)}
        style={[styles.stage, { width, marginLeft: -inset }, wide && { height: pictureHeight }]}
        {...swipe.panHandlers}>
        <View style={wide ? StyleSheet.absoluteFill : { height: pictureHeight }}>
          {features.map((item, i) => (
            <Backdrop
              key={item.title}
              feature={item}
              active={i === index}
              tone={item.image ? undefined : drawnTone(i)}
              wide={wide}
              width={width}
              height={pictureHeight}
              inset={inset}
            />
          ))}
          <View style={styles.awning}>
            <Awning stripes={Math.max(12, Math.round(width / 40))} height={AWNING_HEIGHT} />
          </View>
        </View>

        <View
          style={[
            styles.card,
            wide ? [styles.cardWide, { left: inset }] : { marginHorizontal: inset, marginTop: -CARD_OVERLAP },
            { backgroundColor: theme.surface, borderColor: theme.border },
          ]}>
          <Animated.View
            key={index}
            entering={(direction === 1 ? FadeInRight : FadeInLeft).duration(260)}
            style={styles.cardText}
            accessibilityLiveRegion={playing ? 'none' : 'polite'}>
            <View style={styles.cardHead}>
              <View style={[styles.cardIcon, { backgroundColor: theme.primaryMuted }]}>
                <Icon name={feature.icon} size={20} color="primary" />
              </View>
              <ThemedText type="small" themeColor="textSecondary">
                {index + 1} z {count}
              </ThemedText>
            </View>
            <ThemedText type={wide ? 'title' : 'subtitle'}>{feature.title}</ThemedText>
            <ThemedText type={wide ? 'lead' : 'default'} themeColor="textSecondary">
              {feature.text}
            </ThemedText>
          </Animated.View>

          <View style={styles.controls}>
            <View style={styles.dots}>
              {features.map((item, i) => (
                <Pressable
                  key={item.title}
                  accessibilityRole="button"
                  accessibilityLabel={`Slajd ${i + 1}: ${item.title}`}
                  accessibilityState={{ selected: i === index }}
                  hitSlop={Spacing.two}
                  onPress={() => go(i)}
                  style={[
                    styles.dot,
                    i === index && styles.dotActive,
                    {
                      backgroundColor: i === index ? theme.primary : theme.border,
                    },
                  ]}
                />
              ))}
            </View>
            <View style={styles.buttons}>
              {reduceMotion ? null : (
                <RoundButton
                  icon={paused ? 'play' : 'pause'}
                  label={paused ? 'Wznów pokaz slajdów' : 'Zatrzymaj pokaz slajdów'}
                  onPress={() => setPaused((p) => !p)}
                />
              )}
              <RoundButton icon="chevronLeft" label="Poprzedni slajd" onPress={() => go(index - 1)} />
              <RoundButton icon="chevron" label="Następny slajd" onPress={() => go(index + 1)} />
            </View>
          </View>
        </View>
      </Pressable>
    </View>
  );
}

type BackdropProps = {
  feature: Feature;
  active: boolean;
  /** Background of a drawn slide; photo slides leave it out. */
  tone: string | undefined;
  wide: boolean;
  /** Size of the picture area the backdrop fills. */
  width: number;
  height: number;
  inset: number;
};

/** One slide's background. All of them stay mounted so changing slides is a cross-fade. */
function Backdrop({ feature, active, tone, wide, width, height, inset }: BackdropProps) {
  const theme = useTheme();
  const fade = useAnimatedStyle(() => ({ opacity: withTiming(active ? 1 : 0, { duration: 600 }) }), [active]);

  if (feature.image) {
    // Cover the area like `resizeMode="cover"`, but keep the photo's focus side in view when cropping.
    const { source, aspectRatio, focus = 'center' } = feature.image;
    const photoWidth = Math.max(width, height * aspectRatio);
    const photoHeight = photoWidth / aspectRatio;
    const spare = width - photoWidth;
    return (
      <Animated.View style={[StyleSheet.absoluteFill, fade]} pointerEvents="none">
        <Image
          source={source}
          accessible={false}
          style={{
            position: 'absolute',
            left: focus === 'left' ? 0 : focus === 'right' ? spare : spare / 2,
            top: (height - photoHeight) / 2,
            width: photoWidth,
            height: photoHeight,
          }}
        />
      </Animated.View>
    );
  }

  // A drawn slide: the feature's icon in a large disc, where a photo would show the product.
  const light = tone === theme.primaryMuted;
  const disc = wide ? Math.round(height * 0.66) : 190;
  // Centre the disc in the part of the picture left visible by the awning and the card.
  const discPosition = wide
    ? { right: inset + Spacing.five, top: (height - disc + AWNING_HEIGHT) / 2 }
    : { alignSelf: 'center' as const, top: (height - disc + AWNING_HEIGHT - CARD_OVERLAP) / 2 };
  return (
    <Animated.View style={[StyleSheet.absoluteFill, { backgroundColor: tone }, fade]} pointerEvents="none">
      <View
        style={[
          styles.disc,
          discPosition,
          {
            width: disc,
            height: disc,
            backgroundColor: light ? theme.surface : 'rgba(255, 255, 255, 0.1)',
          },
        ]}>
        <Icon name={feature.icon} size={Math.round(disc * 0.42)} tintColor={light ? theme.primary : theme.accent} />
      </View>
    </Animated.View>
  );
}

function RoundButton({ icon, label, onPress }: { icon: IconName; label: string; onPress: () => void }) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [
        styles.round,
        {
          borderColor: theme.border,
          backgroundColor: pressed ? theme.surfaceMuted : theme.surface,
        },
      ]}>
      <Icon name={icon} size={20} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  stage: {
    overflow: 'hidden',
  },
  awning: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
  },
  disc: {
    position: 'absolute',
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
  },
  card: {
    gap: Spacing.four,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  cardWide: {
    position: 'absolute',
    bottom: Spacing.five,
    width: 460,
  },
  cardText: {
    gap: Spacing.two,
  },
  cardHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: Spacing.one,
  },
  cardIcon: {
    width: 40,
    height: 40,
    borderRadius: Radius.small,
    alignItems: 'center',
    justifyContent: 'center',
  },
  controls: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: Spacing.three,
  },
  dots: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  dotActive: {
    width: 24,
  },
  buttons: {
    flexDirection: 'row',
    gap: Spacing.two,
  },
  round: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
