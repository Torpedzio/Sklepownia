import { NativeTabs } from 'expo-router/native-tabs';

import { useTheme } from '@/hooks/use-theme';

export default function AppTabs() {
  const theme = useTheme();

  return (
    <NativeTabs
      backgroundColor={theme.surface}
      indicatorColor={theme.primaryMuted}
      tintColor={theme.primary}
      labelStyle={{ selected: { color: theme.primary } }}>
      <NativeTabs.Trigger name="shops">
        <NativeTabs.Trigger.Label>Sklepy</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="storefront" md="storefront" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="help">
        <NativeTabs.Trigger.Label>Pomoc</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="questionmark.circle" md="help" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="account">
        <NativeTabs.Trigger.Label>Konto</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="person.crop.circle" md="account_circle" />
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
