import { LinearGradient } from 'expo-linear-gradient';
import { useState, type ReactNode } from 'react';
import { Image, StyleSheet, View } from 'react-native';
import { useReducedMotion } from 'react-native-reanimated';

import { usePageScroll, type PageScroll } from '@/components/page';
import { PinnedSequence, SectionHeader, SwapLayer } from '@/components/pinned-sequence';
import { ThemedText } from '@/components/themed-text';
import { ThemePreviewAspectRatio, Themes } from '@/constants/content';
import { Spacing, WideBreakpoint } from '@/constants/theme';
import { useFullBleed } from '@/hooks/use-full-bleed';
import { useTheme } from '@/hooks/use-theme';

// Share of the page width the screenshot takes on wide screens, and its largest width.
const PREVIEW_SHARE = 0.66;
const PREVIEW_MAX_WIDTH = 1000;
const TEXT_WIDTH = 400;
// Used until the narrow bands have been measured.
const NARROW_TEXT_ESTIMATE = 220;

type Theme = (typeof Themes)[number];
type ShowcaseProps = { title: string; text: string };

/**
 * The themes as full-width bands: a screenshot fading into the page colour, the description on the fade.
 * While the page scrolls through the section, its header and stage stay pinned and a short scroll swaps
 * the theme on the stage for the next one (PinnedSequence). With reduced motion, or outside a Page,
 * the bands are a plain list.
 */
export function ThemeShowcase({ title, text }: ShowcaseProps) {
  const reduceMotion = useReducedMotion();
  const page = usePageScroll();
  const header = <SectionHeader title={title} text={text} />;
  return page && !reduceMotion ? <StackedShowcase header={header} page={page} /> : <ListShowcase header={header} />;
}

function ListShowcase({ header }: { header: ReactNode }) {
  const { columnRef, onColumnLayout, inset, width } = useFullBleed();
  const wide = width >= WideBreakpoint;
  return (
    <View ref={columnRef} onLayout={onColumnLayout} style={styles.section}>
      {header}
      <View style={styles.list}>
        {Themes.map((item, index) => (
          <View key={item.name} style={{ width, marginLeft: -inset }}>
            {wide ? (
              <WideBand theme={item} index={index} width={width} inset={inset} previewWidth={previewWidthFor(width)} />
            ) : (
              <NarrowBand theme={item} width={width} inset={inset} />
            )}
          </View>
        ))}
      </View>
    </View>
  );
}

function StackedShowcase({ header, page }: { header: ReactNode; page: PageScroll }) {
  const { columnRef, onColumnLayout, inset, width } = useFullBleed();
  const wide = width >= WideBreakpoint;
  const [narrowHeight, setNarrowHeight] = useState(0);
  // The pinned stage fills the screen, so nothing else shows below it while pinned.
  const previewWidthIn = (room: number) => previewWidthFor(width, room, Infinity);

  return (
    <View ref={columnRef} onLayout={onColumnLayout}>
      <PinnedSequence
        header={header}
        count={Themes.length}
        page={page}
        stageHeight={(room) =>
          wide
            ? Math.round(previewWidthIn(room) / ThemePreviewAspectRatio)
            : narrowHeight || Math.round(width / ThemePreviewAspectRatio) + NARROW_TEXT_ESTIMATE
        }>
        {(active, height) => (
          <View style={[styles.stage, { width, height, marginLeft: -inset }]}>
            {Themes.map((item, index) => (
              <SwapLayer key={item.name} index={index} active={active}>
                {wide ? (
                  <WideBand
                    theme={item}
                    index={index}
                    width={width}
                    inset={inset}
                    previewWidth={Math.round(height * ThemePreviewAspectRatio)}
                  />
                ) : (
                  <NarrowBand
                    theme={item}
                    width={width}
                    inset={inset}
                    onHeight={(measured) => setNarrowHeight((current) => Math.max(current, measured))}
                  />
                )}
              </SwapLayer>
            ))}
          </View>
        )}
      </PinnedSequence>
    </View>
  );
}

function previewWidthFor(width: number, maxHeight = Infinity, maxWidth = PREVIEW_MAX_WIDTH) {
  return Math.round(Math.min(width * PREVIEW_SHARE, maxWidth, maxHeight * ThemePreviewAspectRatio));
}

type BandProps = { theme: Theme; width: number; inset: number };

function WideBand({
  theme: item,
  index,
  width,
  inset,
  previewWidth,
}: BandProps & { index: number; previewWidth: number }) {
  const theme = useTheme();
  // Screenshots alternate sides, starting on the right.
  const side = index % 2 === 0 ? 'right' : 'left';
  const height = Math.round(previewWidth / ThemePreviewAspectRatio);
  const fadeWidth = Math.round(previewWidth * 0.5);
  const clear = `${theme.background}00`;
  // The fade starts at the screenshot's inner edge, the one facing the text.
  const fade = side === 'right' ? { left: width - previewWidth } : { left: previewWidth - fadeWidth };

  return (
    <View style={[styles.band, { width, height }]}>
      <Image
        source={item.preview}
        accessibilityLabel={`Podgląd sklepu ${item.platform} z motywem ${item.name}`}
        style={[styles.preview, { width: previewWidth, height }, side === 'right' ? { right: 0 } : { left: 0 }]}
      />
      <LinearGradient
        colors={side === 'right' ? [theme.background, clear] : [clear, theme.background]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 0 }}
        pointerEvents="none"
        style={[styles.fade, { width: fadeWidth }, fade]}
      />
      <LinearGradient
        colors={[clear, theme.background]}
        pointerEvents="none"
        style={[styles.bottomFade, side === 'right' ? { right: 0 } : { left: 0 }, { width: previewWidth }]}
      />
      <View style={[styles.wideText, side === 'right' ? { left: inset } : { right: inset }]}>
        <Description theme={item} />
      </View>
    </View>
  );
}

function NarrowBand({ theme: item, width, inset, onHeight }: BandProps & { onHeight?: (height: number) => void }) {
  const theme = useTheme();
  const height = Math.round(width / ThemePreviewAspectRatio);
  return (
    <View style={{ width }} onLayout={onHeight && ((event) => onHeight(Math.ceil(event.nativeEvent.layout.height)))}>
      <View style={{ height }}>
        <Image
          source={item.preview}
          accessibilityLabel={`Podgląd sklepu ${item.platform} z motywem ${item.name}`}
          style={[styles.preview, { width, height }]}
        />
        <LinearGradient
          colors={[`${theme.background}00`, theme.background]}
          pointerEvents="none"
          style={[styles.narrowFade, { height: height * 0.6 }]}
        />
      </View>
      <View style={[styles.narrowText, { paddingHorizontal: inset }]}>
        <Description theme={item} />
      </View>
    </View>
  );
}

function Description({ theme: item }: { theme: Theme }) {
  return (
    <>
      <ThemedText type="smallBold" themeColor="primary">
        {item.platform}
      </ThemedText>
      <ThemedText type="title">{item.name}</ThemedText>
      <ThemedText type="lead" themeColor="textSecondary">
        {item.text}
      </ThemedText>
    </>
  );
}

const styles = StyleSheet.create({
  section: {
    gap: Spacing.four,
  },
  list: {
    gap: Spacing.five,
  },
  stage: {
    overflow: 'hidden',
  },
  band: {
    overflow: 'hidden',
  },
  preview: {
    position: 'absolute',
    top: 0,
  },
  fade: {
    position: 'absolute',
    top: 0,
    bottom: 0,
  },
  bottomFade: {
    position: 'absolute',
    bottom: 0,
    height: 96,
  },
  wideText: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    width: TEXT_WIDTH,
    justifyContent: 'center',
    gap: Spacing.two,
  },
  narrowFade: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
  },
  narrowText: {
    marginTop: -Spacing.four,
    gap: Spacing.two,
  },
});
