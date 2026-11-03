import type { PropsWithChildren, ReactNode } from 'react';
import { ScrollView, StyleSheet, View, type ScrollViewProps } from 'react-native';

import { KeyboardArea } from '@/components/keyboard-area';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

type PageProps = PropsWithChildren<
  ScrollViewProps & {
    maxWidth?: number;
    /** Rendered full-width above the centered content (e.g. the awning and site header). */
    top?: ReactNode;
    /** Rendered full-width below the centered content (e.g. the footer). */
    bottom?: ReactNode;
  }
>;

export function Page({ children, maxWidth = MaxContentWidth, top, bottom, contentContainerStyle, ...rest }: PageProps) {
  const theme = useTheme();
  return (
    <KeyboardArea>
      <ScrollView
        style={{ backgroundColor: theme.background }}
        contentContainerStyle={styles.scroll}
        contentInsetAdjustmentBehavior="automatic"
        keyboardShouldPersistTaps="handled"
        automaticallyAdjustKeyboardInsets
        {...rest}>
        {top}
        <View style={[styles.content, { maxWidth }, contentContainerStyle]}>{children}</View>
        {bottom}
      </ScrollView>
    </KeyboardArea>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flexGrow: 1,
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
