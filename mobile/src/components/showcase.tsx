import { LinearGradient } from 'expo-linear-gradient';
import { useState, type ReactNode } from 'react';
import { Image, StyleSheet, View } from 'react-native';

import { usePageScroll, type PageScroll } from '@/components/page';
import { PinnedSequence, SectionHeader, SwapLayer } from '@/components/pinned-sequence';
import { ThemedText } from '@/components/themed-text';
import { PreviewAspectRatio, type ShowcaseItem } from '@/constants/content';
import { clearOf, Spacing, WideBreakpoint } from '@/constants/theme';
import { useFullBleed } from '@/hooks/use-full-bleed';
import { useReducedMotion } from '@/hooks/use-reduced-motion';
import { useTheme } from '@/hooks/use-theme';

// The screenshot's share of the page width on wide screens.
const PREVIEW_SHARE = 0.66;
const PREVIEW_MAX_WIDTH = 1000;
const TEXT_WIDTH = 400;
const NARROW_TEXT_ESTIMATE = 220;

type ShowcaseProps = { title: string; text: string; items: ShowcaseItem[] };

/** Full-width screenshot bands, pinned while scrolling (PinnedSequence); a plain list with reduced motion or outside a Page. */
export function Showcase({ title, text, items }: ShowcaseProps) {
  const reduceMotion = useReducedMotion();
  const page = usePageScroll();
  const header = <SectionHeader title={title} text={text} />;
  return page && !reduceMotion ? (
    <StackedShowcase header={header} page={page} items={items} />
  ) : (
    <ListShowcase header={header} items={items} />
  );
}

function ListShowcase({ header, items }: { header: ReactNode; items: ShowcaseItem[] }) {
  const { columnRef, onColumnLayout, inset, width } = useFullBleed();
  const wide = width >= WideBreakpoint;
  return (
    <View ref={columnRef} onLayout={onColumnLayout} style={styles.section}>
      {header}
      <View style={styles.list}>
        {items.map((item, index) => (
          <View key={item.name} style={{ width, marginLeft: -inset }}>
            {wide ? (
              <WideBand item={item} index={index} width={width} inset={inset} previewWidth={previewWidthFor(width)} />
            ) : (
              <NarrowBand item={item} width={width} inset={inset} />
            )}
          </View>
        ))}
      </View>
    </View>
  );
}

function StackedShowcase({ header, page, items }: { header: ReactNode; page: PageScroll; items: ShowcaseItem[] }) {
  const { columnRef, onColumnLayout, inset, width } = useFullBleed();
  const wide = width >= WideBreakpoint;
  const [narrowHeight, setNarrowHeight] = useState(0);
  // The pinned stage fills the screen, so nothing else shows below it while pinned.
  const previewWidthIn = (room: number) => previewWidthFor(width, room, Infinity);

  return (
    <View ref={columnRef} onLayout={onColumnLayout}>
      <PinnedSequence
        header={header}
        count={items.length}
        page={page}
        stageHeight={(room) =>
          wide
            ? Math.round(previewWidthIn(room) / PreviewAspectRatio)
            : narrowHeight || Math.round(width / PreviewAspectRatio) + NARROW_TEXT_ESTIMATE
        }>
        {(active, height) => (
          <View style={[styles.stage, { width, height, marginLeft: -inset }]}>
            {items.map((item, index) => (
              <SwapLayer key={item.name} index={index} active={active}>
                {wide ? (
                  <WideBand
                    item={item}
                    index={index}
                    width={width}
                    inset={inset}
                    previewWidth={Math.round(height * PreviewAspectRatio)}
                  />
                ) : (
                  <NarrowBand
                    item={item}
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
  return Math.round(Math.min(width * PREVIEW_SHARE, maxWidth, maxHeight * PreviewAspectRatio));
}

type BandProps = { item: ShowcaseItem; width: number; inset: number };

function WideBand({
  item,
  index,
  width,
  inset,
  previewWidth,
}: BandProps & { index: number; previewWidth: number }) {
  const theme = useTheme();
  const side = index % 2 === 0 ? 'right' : 'left';
  const height = Math.round(previewWidth / PreviewAspectRatio);
  const fadeWidth = Math.round(previewWidth * 0.5);
  const clear = clearOf(theme.background);
  // The fade starts at the screenshot's edge facing the text.
  const fade = side === 'right' ? { left: width - previewWidth } : { left: previewWidth - fadeWidth };

  return (
    <View style={[styles.band, { width, height }]}>
      <Image
        source={item.preview}
        accessibilityLabel={item.alt}
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
        <Description item={item} />
      </View>
    </View>
  );
}

function NarrowBand({ item, width, inset, onHeight }: BandProps & { onHeight?: (height: number) => void }) {
  const theme = useTheme();
  const height = Math.round(width / PreviewAspectRatio);
  return (
    <View style={{ width }} onLayout={onHeight && ((event) => onHeight(Math.ceil(event.nativeEvent.layout.height)))}>
      <View style={{ height }}>
        <Image
          source={item.preview}
          accessibilityLabel={item.alt}
          style={[styles.preview, { width, height }]}
        />
        <LinearGradient
          colors={[clearOf(theme.background), theme.background]}
          pointerEvents="none"
          style={[styles.narrowFade, { height: height * 0.6 }]}
        />
      </View>
      <View style={[styles.narrowText, { paddingHorizontal: inset }]}>
        <Description item={item} />
      </View>
    </View>
  );
}

function Description({ item }: { item: ShowcaseItem }) {
  return (
    <>
      <ThemedText type="smallBold" themeColor="primary">
        {item.label}
      </ThemedText>
      <ThemedText type="title">{item.name}</ThemedText>
      <ThemedText type="lead" themeColor="textSecondary">
        {item.text}
      </ThemedText>
      {item.details ? (
        <ThemedText type="small" themeColor="textSecondary">
          {item.details}
        </ThemedText>
      ) : null}
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
