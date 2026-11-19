import { Link } from 'expo-router';
import type { PropsWithChildren } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Awning } from '@/components/awning';
import { KeyboardArea } from '@/components/keyboard-area';
import { Logo } from '@/components/logo';
import { Receipt } from '@/components/receipt';
import { ThemedText } from '@/components/themed-text';
import { SetupSteps } from '@/constants/content';
import { Spacing, WideBreakpoint } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { useWindowDimensions } from '@/hooks/use-window-dimensions';

type AuthLayoutProps = PropsWithChildren<{ title: string; subtitle?: string }>;

export function AuthLayout({ title, subtitle, children }: AuthLayoutProps) {
  const theme = useTheme();
  const { width } = useWindowDimensions();
  const wide = width >= WideBreakpoint;

  return (
    <View style={[styles.flex, styles.row, { backgroundColor: theme.background }]}>
      {wide ? (
        <View style={[styles.panel, { backgroundColor: theme.primary }]}>
          <Awning tone="green" />
          <View style={styles.panelContent}>
            <Link href="/" asChild>
              <Pressable accessibilityRole="link">
                <Logo inverted />
              </Pressable>
            </Link>
            <ThemedText type="title" style={{ color: theme.onPrimary }}>
              Od formularza do otwartego sklepu w niecałe dwie minuty.
            </ThemedText>
            <View style={styles.panelReceipt}>
              <Receipt
                title="Twój sklep"
                rows={SetupSteps.slice(-4).map((step) => ({ label: step.label, value: step.time }))}
                stamp={{ text: 'Otwarte', tone: 'success' }}
              />
            </View>
          </View>
        </View>
      ) : null}

      <SafeAreaView style={styles.flex} edges={['top', 'bottom']}>
        {wide ? null : <Awning />}
        <KeyboardArea>
          <ScrollView
            contentContainerStyle={styles.scroll}
            keyboardShouldPersistTaps="handled"
            automaticallyAdjustKeyboardInsets>
            <View style={styles.form}>
              {wide ? null : (
                <Link href="/" asChild>
                  <Pressable accessibilityRole="link" style={styles.mobileLogo}>
                    <Logo />
                  </Pressable>
                </Link>
              )}
              <View style={styles.heading}>
                <ThemedText type="title">{title}</ThemedText>
                {subtitle ? <ThemedText themeColor="textSecondary">{subtitle}</ThemedText> : null}
              </View>
              {children}
            </View>
          </ScrollView>
        </KeyboardArea>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  row: {
    flexDirection: 'row',
  },
  panel: {
    width: '42%',
    maxWidth: 560,
  },
  panelContent: {
    flex: 1,
    padding: Spacing.five,
    gap: Spacing.five,
    justifyContent: 'space-between',
  },
  panelReceipt: {
    width: 320,
    transform: [{ rotate: '-2deg' }],
  },
  scroll: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: Spacing.four,
  },
  form: {
    width: '100%',
    maxWidth: 420,
    alignSelf: 'center',
    gap: Spacing.three,
  },
  mobileLogo: {
    marginBottom: Spacing.three,
  },
  heading: {
    gap: Spacing.one,
    marginBottom: Spacing.two,
  },
});
