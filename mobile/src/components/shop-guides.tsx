import { useMemo, useState } from "react";
import {
  Linking,
  PanResponder,
  Pressable,
  StyleSheet,
  View,
} from "react-native";
import Animated, { FadeInLeft, FadeInRight } from "react-native-reanimated";

import { Icon } from "@/components/icon";
import { ThemedText } from "@/components/themed-text";
import { Button } from "@/components/ui/button";
import { ShopGuides } from "@/constants/shop-guides";
import { Fonts, Radius, Spacing } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";

type ShopGuidesPanelProps = {
  /** When given, each tip gets a button opening the right page of this shop's admin panel. */
  shopUrl?: string;
};

// Every tip of every category in one sequence, so "Next" carries on into the next category.
const SLIDES = ShopGuides.flatMap((guide, guideIndex) =>
  guide.tips.map((tip, tipIndex) => ({ guide, guideIndex, tip, tipIndex })),
);
const SWIPE_DISTANCE = 50;

/** Tips for setting up and running a shop, shown one slide at a time. */
export function ShopGuidesPanel({ shopUrl }: ShopGuidesPanelProps) {
  const theme = useTheme();
  const [index, setIndex] = useState(0);
  const [direction, setDirection] = useState<1 | -1>(1);
  const slide = SLIDES[index];
  const { guide, tip, tipIndex } = slide;
  const isLast = index === SLIDES.length - 1;
  const nextGuide = ShopGuides[slide.guideIndex + 1];
  const endsCategory = tipIndex === guide.tips.length - 1;

  function go(to: number) {
    setDirection(to >= index ? 1 : -1);
    setIndex((to + SLIDES.length) % SLIDES.length);
  }

  const swipe = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, g) =>
          Math.abs(g.dx) > 12 && Math.abs(g.dx) > Math.abs(g.dy) * 1.5,
        onPanResponderRelease: (_, g) => {
          if (g.dx <= -SWIPE_DISTANCE) {
            setDirection(1);
            setIndex((i) => (i + 1) % SLIDES.length);
          } else if (g.dx >= SWIPE_DISTANCE) {
            setDirection(-1);
            setIndex((i) => Math.max(i - 1, 0));
          }
        },
      }),
    [],
  );

  const nextLabel = isLast
    ? "Od początku"
    : endsCategory && nextGuide
      ? `Dalej: ${nextGuide.label}`
      : "Dalej";

  return (
    <View
      style={[
        styles.panel,
        { backgroundColor: theme.surface, borderColor: theme.border },
      ]}
    >
      <View style={styles.head}>
        <ThemedText type="subtitle">Porady</ThemedText>
        <View style={styles.tabs} accessibilityRole="tablist">
          {ShopGuides.map((g, guideIndex) => {
            const active = guideIndex === slide.guideIndex;
            return (
              <Pressable
                key={g.key}
                accessibilityRole="tab"
                accessibilityState={{ selected: active }}
                onPress={() =>
                  go(SLIDES.findIndex((s) => s.guideIndex === guideIndex))
                }
                style={[
                  styles.tab,
                  {
                    backgroundColor: active
                      ? theme.primaryMuted
                      : theme.surfaceMuted,
                  },
                ]}
              >
                <Icon
                  name={g.icon}
                  size={16}
                  color={active ? "primary" : "textSecondary"}
                />
                <ThemedText
                  type="smallBold"
                  themeColor={active ? "primary" : "textSecondary"}
                >
                  {g.label}
                </ThemedText>
              </Pressable>
            );
          })}
        </View>
      </View>

      <View
        {...swipe.panHandlers}
        style={[styles.stage, { backgroundColor: theme.background }]}
      >
        <Animated.View
          key={index}
          entering={(direction === 1 ? FadeInRight : FadeInLeft).duration(220)}
          style={styles.slide}
          accessibilityLiveRegion="polite"
        >
          <View style={styles.slideTop}>
            <View
              style={[
                styles.marker,
                {
                  backgroundColor: guide.ordered
                    ? theme.accent
                    : theme.primaryMuted,
                },
              ]}
            >
              {guide.ordered ? (
                <ThemedText style={[styles.number, { color: theme.onAccent }]}>
                  {tipIndex + 1}
                </ThemedText>
              ) : (
                <Icon name={guide.icon} size={18} color="primary" />
              )}
            </View>
            <ThemedText type="small" themeColor="textSecondary">
              {guide.ordered ? "Krok" : "Porada"} {tipIndex + 1} z{" "}
              {guide.tips.length}
            </ThemedText>
          </View>
          <ThemedText type="subtitle">{tip.title}</ThemedText>
          <ThemedText
            type="lead"
            themeColor="textSecondary"
            style={styles.text}
          >
            {tip.text}
          </ThemedText>
          <View style={styles.slideBottom}>
            <View
              style={[styles.menu, { backgroundColor: theme.surfaceMuted }]}
            >
              <Icon name="chevron" size={14} color="textSecondary" />
              <ThemedText type="small" style={styles.menuText}>
                {tip.menu}
              </ThemedText>
            </View>
            {shopUrl ? (
              <Button
                title="Otwórz w panelu"
                variant="secondary"
                icon="external"
                accessibilityLabel={`${tip.title}: otwórz w panelu sklepu`}
                onPress={() =>
                  Linking.openURL(`${shopUrl}/wp-admin/${tip.adminPath}`)
                }
              />
            ) : null}
          </View>
        </Animated.View>
      </View>

      <View style={styles.dots}>
        {guide.tips.map((t, i) => {
          const target = SLIDES.findIndex(
            (s) => s.guideIndex === slide.guideIndex && s.tipIndex === i,
          );
          const current = i === tipIndex;
          return (
            <Pressable
              key={t.title}
              accessibilityRole="button"
              accessibilityLabel={`Porada ${i + 1}: ${t.title}`}
              accessibilityState={{ selected: current }}
              hitSlop={6}
              onPress={() => go(target)}
              style={[
                styles.dot,
                current && styles.dotCurrent,
                { backgroundColor: current ? theme.primary : theme.border },
              ]}
            />
          );
        })}
      </View>
      <View style={styles.controls}>
        <Button
          title="Wstecz"
          variant="ghost"
          onPress={() => go(index - 1)}
          disabled={index === 0}
        />
        <Button title={nextLabel} onPress={() => go(index + 1)} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  head: {
    gap: Spacing.three,
  },
  tabs: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: Spacing.two,
  },
  tab: {
    flexDirection: "row",
    alignItems: "center",
    gap: Spacing.one + Spacing.half,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: Radius.pill,
  },
  stage: {
    borderRadius: Radius.medium,
    overflow: "hidden",
  },
  slide: {
    gap: Spacing.three,
    padding: Spacing.four,
    minHeight: 280,
  },
  slideTop: {
    flexDirection: "row",
    alignItems: "center",
    gap: Spacing.three,
  },
  marker: {
    width: 36,
    height: 36,
    borderRadius: Radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },
  number: {
    fontFamily: Fonts.display,
    fontSize: 17,
    lineHeight: 22,
  },
  text: {
    maxWidth: 680,
  },
  slideBottom: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: Spacing.three,
    marginTop: "auto",
  },
  menu: {
    flexDirection: "row",
    alignItems: "center",
    flexShrink: 1,
    maxWidth: "100%",
    gap: Spacing.one,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: Radius.small,
  },
  menuText: {
    flexShrink: 1,
  },
  controls: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: Spacing.two,
  },
  dots: {
    flexDirection: "row",
    justifyContent: "center",
    gap: Spacing.two,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  dotCurrent: {
    width: 22,
  },
});
