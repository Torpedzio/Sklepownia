import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { Icon } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

type FaqListProps = { items: { question: string; answer: string }[] };

export function FaqList({ items }: FaqListProps) {
  const theme = useTheme();
  const [open, setOpen] = useState<number | null>(null);

  return (
    <View>
      {items.map((item, index) => {
        const expanded = open === index;
        return (
          <View key={item.question} style={[styles.item, { borderTopColor: theme.border }]}>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ expanded }}
              onPress={() => setOpen(expanded ? null : index)}
              style={styles.question}>
              <ThemedText type="heading" style={styles.questionText}>
                {item.question}
              </ThemedText>
              <View style={{ transform: [{ rotate: expanded ? '180deg' : '0deg' }] }}>
                <Icon name="chevronDown" size={20} color="textSecondary" />
              </View>
            </Pressable>
            {expanded ? (
              <Animated.View entering={FadeIn.duration(200)}>
                <ThemedText themeColor="textSecondary" style={styles.answer}>
                  {item.answer}
                </ThemedText>
              </Animated.View>
            ) : null}
          </View>
        );
      })}
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
  answer: {
    paddingBottom: Spacing.three,
    maxWidth: 640,
  },
});
