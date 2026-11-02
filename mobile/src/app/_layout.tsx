import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { useColorScheme } from 'react-native';

import { AuthProvider, useAuth } from '@/context/auth';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const colorScheme = useColorScheme();
  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <AuthProvider>
        <RootNavigator />
      </AuthProvider>
    </ThemeProvider>
  );
}

function RootNavigator() {
  const { isLoading, user } = useAuth();

  useEffect(() => {
    if (!isLoading) SplashScreen.hideAsync();
  }, [isLoading]);

  if (isLoading) return null;

  return (
    <Stack screenOptions={{ headerBackButtonDisplayMode: 'minimal' }}>
      <Stack.Protected guard={!user}>
        <Stack.Screen name="sign-in" options={{ headerShown: false }} />
        <Stack.Screen name="sign-up" options={{ title: 'Załóż konto' }} />
      </Stack.Protected>
      <Stack.Protected guard={!!user && !user.is_email_verified}>
        <Stack.Screen name="verify-email" options={{ title: 'Potwierdź e-mail' }} />
      </Stack.Protected>
      <Stack.Protected guard={!!user?.is_email_verified}>
        <Stack.Screen name="index" options={{ title: 'Moje sklepy' }} />
        <Stack.Screen name="shops/new" options={{ title: 'Nowy sklep', presentation: 'modal' }} />
        <Stack.Screen name="shops/[id]" options={{ title: 'Sklep' }} />
      </Stack.Protected>
    </Stack>
  );
}
