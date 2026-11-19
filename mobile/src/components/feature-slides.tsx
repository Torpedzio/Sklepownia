import { LinearGradient } from 'expo-linear-gradient';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Image, PanResponder, Pressable, StyleSheet, View } from 'react-native';
import Animated, { FadeInLeft, FadeInRight, useAnimatedStyle, withTiming } from 'react-native-reanimated';

import { Awning, AWNING_HEIGHT } from '@/components/awning';
import { Icon, type IconName } from '@/components/icon';
import { usePageScroll, type PageScroll } from '@/components/page';
import { PinnedSequence, SectionHeader, SwapLayer } from '@/components/pinned-sequence';
import { ThemedText } from '@/components/themed-text';
import type { Feature } from '@/constants/content';
import { clearOf, Radius, Spacing, WideBreakpoint } from '@/constants/theme';
import { useFullBleed } from '@/hooks/use-full-bleed';
import { useReducedMotion } from '@/hooks/use-reduced-motion';
import { useTheme } from '@/hooks/use-theme';
import { useWindowDimensions } from '@/hooks/use-window-dimensions';

const AUTOPLAY_MS = 7000;
const SWIPE_DISTANCE = 50;
// Narrow screens: the card sits under the picture, overlapping it.
const NARROW_PICTURE_HEIGHT = 340;
const CARD_OVERLAP = 48;
const NARROW_CARD_ESTIMATE = 300;
// Fractions of the width a photo fades over at each side.
const SIDE_FADE_WIDE = 0.2;
const SIDE_FADE_NARROW = 0.12;

/** One slide per feature, pinned while scrolling (PinnedSequence); a slideshow with reduced motion or outside a Page. */
export function FeatureSlides({ features, title }: { features: Feature[]; title: string }) {
  const reduceMotion = useReducedMotion();
  const page = usePageScroll();
  const header = <SectionHeader title={title} />;
  if (page && !reduceMotion) return <PinnedSlides header={header} features={features} page={page} />;
  return (
    <View style={styles.section}>
      {header}
      <SlideShow features={features} />
    </View>
  );
}

function PinnedSlides({ header, features, page }: { header: ReactNode; features: Feature[]; page: PageScroll }) {
  const theme = useTheme();
  const { columnRef, onColumnLayout, inset, width } = useFullBleed();
  const wide = width >= WideBreakpoint;
  const [narrowHeight, setNarrowHeight] = useState(0);
  const tone = drawnTones(features, theme);

  return (
    <View ref={columnRef} onLayout={onColumnLayout}>
      <PinnedSequence
        header={header}
        count={features.length}
        page={page}
        stageHeight={(room) =>
          wide
            ? Math.round(Math.min(Math.max(room, 420), 760))
            : narrowHeight || NARROW_PICTURE_HEIGHT - CARD_OVERLAP + NARROW_CARD_ESTIMATE
        }>
        {(active, height) => (
          <View style={[styles.stage, { width, height, marginLeft: -inset }]}>
            {features.map((feature, index) => (
              <SwapLayer key={feature.title} index={index} active={active}>
                <View
                  style={wide ? StyleSheet.absoluteFill : undefined}
                  onLayout={
                    wide
                      ? undefined
                      : (event) => {
                          const measured = Math.ceil(event.nativeEvent.layout.height);
                          setNarrowHeight((current) => Math.max(current, measured));
                        }
                  }>
                  <View style={wide ? StyleSheet.absoluteFill : { height: NARROW_PICTURE_HEIGHT }}>
                    <Backdrop
                      feature={feature}
                      active
                      tone={tone(index)}
                      wide={wide}
                      width={width}
                      height={wide ? height : NARROW_PICTURE_HEIGHT}
                      inset={inset}
                    />
                  </View>
                  <View
                    style={[
                      styles.card,
                      wide ? [styles.cardWide, { left: inset }] : { marginHorizontal: inset, marginTop: -CARD_OVERLAP },
                      { backgroundColor: theme.surface, borderColor: theme.border },
                    ]}>
                    <SlideText feature={feature} index={index} count={features.length} wide={wide} />
                  </View>
                </View>
              </SwapLayer>
            ))}
            <View style={styles.awning}>
              <Awning />
            </View>
          </View>
        )}
      </PinnedSequence>
    </View>
  );
}

function drawnTones(features: Feature[], theme: ReturnType<typeof useTheme>) {
  const tones = [theme.primary, '#14213D', theme.primaryMuted];
  return (index: number) =>
    features[index].image
      ? undefined
      : tones[features.slice(0, index).filter((item) => !item.image).length % tones.length];
}

function SlideText({ feature, index, count, wide }: { feature: Feature; index: number; count: number; wide: boolean }) {
  const theme = useTheme();
  return (
    <>
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
    </>
  );
}

/** The reduced-motion version: advances on its own until hovered or paused. */
function SlideShow({ features }: { features: Feature[] }) {
  const theme = useTheme();
  const { height } = useWindowDimensions();
  const { columnRef, onColumnLayout, inset, width } = useFullBleed();
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
  const tone = drawnTones(features, theme);

  return (
    <View ref={columnRef} onLayout={onColumnLayout}>
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
              tone={tone(i)}
              wide={wide}
              width={width}
              height={pictureHeight}
              inset={inset}
            />
          ))}
          <View style={styles.awning}>
            <Awning />
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
            <SlideText feature={feature} index={index} count={count} wide={wide} />
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
  /** Undefined for photo slides. */
  tone: string | undefined;
  wide: boolean;
  width: number;
  height: number;
  inset: number;
};

/** All backdrops stay mounted, so changing slides is a cross-fade. */
function Backdrop({ feature, active, tone, wide, width, height, inset }: BackdropProps) {
  const theme = useTheme();
  const fade = useAnimatedStyle(() => ({ opacity: withTiming(active ? 1 : 0, { duration: 600 }) }), [active]);

  if (feature.image) {
    // Cover the area like `resizeMode="cover"`, but keep the photo's focus side in view when cropping.
    const { source, aspectRatio, focus = 'center' } = feature.image;
    const photoWidth = Math.max(width, height * aspectRatio);
    const photoHeight = photoWidth / aspectRatio;
    const spare = width - photoWidth;
    const sideFade = Math.round(width * (wide ? SIDE_FADE_WIDE : SIDE_FADE_NARROW));
    const clear = clearOf(theme.background);
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
        <LinearGradient
          colors={[theme.background, clear]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 0 }}
          style={[styles.sideFade, { left: 0, width: sideFade }]}
        />
        <LinearGradient
          colors={[clear, theme.background]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 0 }}
          style={[styles.sideFade, { right: 0, width: sideFade }]}
        />
      </Animated.View>
    );
  }

  const light = tone === theme.primaryMuted;
  const disc = wide ? Math.round(height * 0.66) : 190;
  // Centre the disc in the part left visible by the awning and the card.
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
  section: {
    gap: Spacing.four,
  },
  stage: {
    overflow: 'hidden',
  },
  awning: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
  },
  sideFade: {
    position: 'absolute',
    top: 0,
    bottom: 0,
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
