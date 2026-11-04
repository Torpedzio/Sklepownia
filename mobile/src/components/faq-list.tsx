import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

import { Icon } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

type FaqItem = { question: string; answer: string };
type FaqListProps = { items: FaqItem[] };

const EXPAND_MS = 260;

/** Questions that open one at a time, the answer sliding open below the question. */
export function FaqList({ items }: FaqListProps) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <View>
      {items.map((item, index) => (
        <FaqRow
          key={item.question}
          item={item}
          expanded={open === index}
          onToggle={() => setOpen(open === index ? null : index)}
        />
      ))}
    </View>
  );
}

function FaqRow({ item, expanded, onToggle }: { item: FaqItem; expanded: boolean; onToggle: () => void }) {
  const theme = useTheme();
  // The answer is laid out at full height out of view, so its height is known before it opens.
  const [answerHeight, setAnswerHeight] = useState(0);
  const progress = useSharedValue(0);
  useEffect(() => {
    progress.set(withTiming(expanded ? 1 : 0, { duration: EXPAND_MS }));
  }, [expanded, progress]);
  const reveal = useAnimatedStyle(
    () => ({ height: answerHeight * progress.get(), opacity: progress.get() }),
    [answerHeight],
  );
  const turn = useAnimatedStyle(() => ({ transform: [{ rotate: `${progress.get() * 180}deg` }] }));

  return (
    <View style={[styles.item, { borderTopColor: theme.border }]}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        onPress={onToggle}
        style={styles.question}>
        <ThemedText type="heading" style={styles.questionText}>
          {item.question}
        </ThemedText>
        <Animated.View style={turn}>
          <Icon name="chevronDown" size={20} color="textSecondary" />
        </Animated.View>
      </Pressable>
      <Animated.View
        style={[styles.answerClip, reveal]}
        aria-hidden={!expanded}
        pointerEvents={expanded ? 'auto' : 'none'}>
        <View
          style={styles.answerBody}
          onLayout={(event) => setAnswerHeight(Math.ceil(event.nativeEvent.layout.height))}>
          <ThemedText themeColor="textSecondary" style={styles.answer}>
            {item.answer}
          </ThemedText>
        </View>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  item: {
    borderTopWidth: 1,
  },
  question: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
    paddingVertical: Spacing.three,
  },
  questionText: {
    flex: 1,
  },
  answerClip: {
    overflow: 'hidden',
  },
  answerBody: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
  },
  answer: {
    paddingBottom: Spacing.three,
    maxWidth: 640,
  },
});
