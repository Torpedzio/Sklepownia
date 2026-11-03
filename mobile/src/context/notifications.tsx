import { createContext, Fragment, use, useEffect, useMemo, useState, type PropsWithChildren } from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';
import Animated, { SlideInUp, SlideOutUp } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { FullWindowOverlay } from 'react-native-screens';

import { Icon } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import { Fonts, MaxContentWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

type Tone = 'success' | 'error';
type Notification = { id: number; tone: Tone; message: string };
type Notify = { success: (message: string) => void; error: (message: string) => void };

// Errors stay longer: they usually tell the reader what to do next.
const DURATION: Record<Tone, number> = { success: 4000, error: 7000 };

const NotifyContext = createContext<Notify | null>(null);
let nextId = 0;

export function NotificationsProvider({ children }: PropsWithChildren) {
  const [current, setCurrent] = useState<Notification | null>(null);
  const notify = useMemo<Notify>(
    () => ({
      success: (message) => setCurrent({ id: ++nextId, tone: 'success', message }),
      error: (message) => setCurrent({ id: ++nextId, tone: 'error', message }),
    }),
    [],
  );

  useEffect(() => {
    if (!current) return;
    const timer = setTimeout(() => setCurrent(null), DURATION[current.tone]);
    return () => clearTimeout(timer);
  }, [current]);

  return (
    <NotifyContext value={notify}>
      {children}
      <NotificationBar notification={current} onDismiss={() => setCurrent(null)} />
    </NotifyContext>
  );
}

export function useNotify() {
  const context = use(NotifyContext);
  if (!context) throw new Error('useNotify must be used inside NotificationsProvider');
  return context;
}

// iOS presents modals in their own window, so the bar needs a window above them to stay visible.
const Overlay = Platform.OS === 'ios' ? FullWindowOverlay : Fragment;

function NotificationBar({ notification, onDismiss }: { notification: Notification | null; onDismiss: () => void }) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const isError = notification?.tone === 'error';
  const ink = isError ? theme.onDanger : theme.onPrimary;

  return (
    <Overlay>
      <View pointerEvents="box-none" style={styles.anchor}>
        {notification ? (
          <Animated.View
            key={notification.id}
            entering={SlideInUp.duration(220)}
            exiting={SlideOutUp.duration(180)}
            role={isError ? 'alert' : 'status'}
            accessibilityLiveRegion={isError ? 'assertive' : 'polite'}
            style={[
              styles.bar,
              { paddingTop: insets.top + Spacing.two, backgroundColor: isError ? theme.danger : theme.success },
            ]}>
            <View style={styles.content}>
              <Icon name={isError ? 'warning' : 'check'} size={20} tintColor={ink} />
              <ThemedText style={[styles.message, { color: ink }]}>{notification.message}</ThemedText>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Zamknij powiadomienie"
                hitSlop={Spacing.two}
                onPress={onDismiss}
                style={({ pressed }) => [styles.close, { opacity: pressed ? 0.6 : 1 }]}>
                <Icon name="close" size={18} tintColor={ink} />
              </Pressable>
            </View>
          </Animated.View>
        ) : null}
      </View>
    </Overlay>
  );
}

const styles = StyleSheet.create({
  anchor: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 1000,
  },
  bar: {
    paddingBottom: Spacing.two + Spacing.one,
    paddingHorizontal: Spacing.three,
  },
  content: {
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two + Spacing.one,
  },
  message: {
    flex: 1,
    fontFamily: Fonts.bodySemiBold,
    fontSize: 15,
    lineHeight: 21,
  },
  close: {
    padding: Spacing.one,
  },
});
