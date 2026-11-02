import { Link, Stack } from 'expo-router';
import { ActivityIndicator, FlatList, Pressable, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { StatusBadge } from '@/components/status-badge';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Button } from '@/components/ui/button';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import type { Shop } from '@/lib/types';

const IN_PROGRESS = ['pending', 'provisioning'];

export default function ShopsScreen() {
  const { signOut } = useAuth();
  const theme = useTheme();
  const { data: shops, error, isLoading, isRefreshing, refresh } = useApiQuery<Shop[]>('/shops/', {
    refetchInterval: (data) => (data?.some((shop) => IN_PROGRESS.includes(shop.status)) ? 3000 : false),
  });

  return (
    <ThemedView style={styles.flex}>
      <Stack.Screen
        options={{
          headerRight: () => (
            <Pressable onPress={signOut} hitSlop={8}>
              <ThemedText type="small" themeColor="primary">
                Wyloguj
              </ThemedText>
            </Pressable>
          ),
        }}
      />
      {isLoading ? (
        <ActivityIndicator style={styles.flex} />
      ) : (
        <FlatList
          data={shops}
          keyExtractor={(shop) => String(shop.id)}
          contentInsetAdjustmentBehavior="automatic"
          contentContainerStyle={styles.list}
          onRefresh={refresh}
          refreshing={isRefreshing}
          ListHeaderComponent={error ? <ThemedText themeColor="danger">{error.message}</ThemedText> : undefined}
          ListEmptyComponent={
            error ? undefined : (
              <View style={styles.empty}>
                <ThemedText type="smallBold">Nie masz jeszcze żadnego sklepu</ThemedText>
                <ThemedText type="small" themeColor="textSecondary">
                  Załóż pierwszy. Zajmie to tylko kilka minut.
                </ThemedText>
              </View>
            )
          }
          renderItem={({ item }) => (
            <Link href={{ pathname: '/shops/[id]', params: { id: item.id } }} asChild>
              <Pressable style={StyleSheet.flatten([styles.card, { backgroundColor: theme.backgroundElement }])}>
                <View style={styles.cardText}>
                  <ThemedText type="smallBold">{item.name}</ThemedText>
                  <ThemedText type="small" themeColor="textSecondary" numberOfLines={1}>
                    {item.url.replace('https://', '')}
                  </ThemedText>
                </View>
                <StatusBadge status={item.status} label={item.status_display} />
              </Pressable>
            </Link>
          )}
        />
      )}
      <SafeAreaView edges={['bottom']} style={styles.footer}>
        <Link href="/shops/new" asChild>
          <Button title="+ Nowy sklep" />
        </Link>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  list: {
    gap: Spacing.two,
    padding: Spacing.three,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
  empty: {
    alignItems: 'center',
    gap: Spacing.one,
    paddingVertical: Spacing.six,
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
    padding: Spacing.three,
    borderRadius: Spacing.three,
  },
  cardText: {
    flex: 1,
    gap: Spacing.half,
  },
  footer: {
    padding: Spacing.three,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
});
