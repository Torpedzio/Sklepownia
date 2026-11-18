import { Link } from 'expo-router';
import { TabList, TabSlot, TabTrigger, Tabs, type TabListProps, type TabTriggerSlotProps } from 'expo-router/ui';
import { Pressable, StyleSheet, View } from 'react-native';

import { Awning } from '@/components/awning';
import { Logo } from '@/components/logo';
import { ThemedText } from '@/components/themed-text';
import { MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useTheme } from '@/hooks/use-theme';
import { useWindowDimensions } from '@/hooks/use-window-dimensions';

export default function AppTabs() {
  return (
    <Tabs style={styles.flex} options={{ backBehavior: 'fullHistory' }}>
      <TabList asChild>
        <NavBar>
          <TabTrigger name="shops" href="/shops" asChild>
            <TabButton>Sklepy</TabButton>
          </TabTrigger>
          <TabTrigger name="help" href="/help" asChild>
            <TabButton>Pomoc</TabButton>
          </TabTrigger>
          <TabTrigger name="account" href="/account" asChild>
            <TabButton>Konto</TabButton>
          </TabTrigger>
        </NavBar>
      </TabList>
      <TabSlot style={styles.flex} />
    </Tabs>
  );
}

function NavBar({ children, ...props }: TabListProps) {
  const theme = useTheme();
  const { user } = useAuth();
  const { width } = useWindowDimensions();

  return (
    <View {...props} style={{ backgroundColor: theme.background }}>
      <Awning />
      <View style={[styles.bar, { borderBottomColor: theme.border }]}>
        <Link href="/" asChild>
          <Pressable accessibilityRole="link" accessibilityLabel="Strona główna">
            <Logo compact={width < 480} />
          </Pressable>
        </Link>
        <View style={styles.tabs}>{children}</View>
        {width >= 760 ? (
          <ThemedText type="small" themeColor="textSecondary" numberOfLines={1} style={styles.user}>
            {user?.email}
          </ThemedText>
        ) : null}
      </View>
    </View>
  );
}

function TabButton({ children, isFocused, ref: _ref, ...props }: TabTriggerSlotProps) {
  const theme = useTheme();
  return (
    <Pressable
      {...props}
      style={({ pressed }) => [
        styles.tab,
        { backgroundColor: isFocused ? theme.primaryMuted : 'transparent', opacity: pressed ? 0.7 : 1 },
      ]}>
      <ThemedText type="smallBold" themeColor={isFocused ? 'primary' : 'textSecondary'}>
        {children}
      </ThemedText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  bar: {
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.four,
    paddingHorizontal: Spacing.four,
    paddingVertical: Spacing.two + Spacing.one,
    borderBottomWidth: 1,
  },
  tabs: {
    flexDirection: 'row',
    gap: Spacing.one,
  },
  tab: {
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: Radius.pill,
  },
  user: {
    marginLeft: 'auto',
    maxWidth: 260,
  },
});
