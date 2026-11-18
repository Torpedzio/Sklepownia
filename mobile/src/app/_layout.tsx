import { BricolageGrotesque_600SemiBold, BricolageGrotesque_700Bold } from '@expo-google-fonts/bricolage-grotesque';
import {
  Figtree_400Regular,
  Figtree_500Medium,
  Figtree_600SemiBold,
  Figtree_700Bold,
} from '@expo-google-fonts/figtree';
import { useFonts } from 'expo-font';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { Platform, useColorScheme } from 'react-native';

import { Colors, Fonts } from '@/constants/theme';
import { AuthProvider, useAuth } from '@/context/auth';
import { NotificationsProvider } from '@/context/notifications';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const [fontsLoaded] = useFonts({
    BricolageGrotesque_600SemiBold,
    BricolageGrotesque_700Bold,
    Figtree_400Regular,
    Figtree_500Medium,
    Figtree_600SemiBold,
    Figtree_700Bold,
  });
  const base = scheme === 'dark' ? DarkTheme : DefaultTheme;
  const colors = Colors[scheme];
  const navigationTheme = {
    ...base,
    colors: {
      ...base.colors,
      primary: colors.primary,
      background: colors.background,
      card: colors.background,
      text: colors.text,
      border: colors.border,
    },
  };

  return (
    <ThemeProvider value={navigationTheme}>
      <NotificationsProvider>
        <AuthProvider>
          <RootNavigator fontsLoaded={fontsLoaded} />
        </AuthProvider>
      </NotificationsProvider>
    </ThemeProvider>
  );
}

function RootNavigator({ fontsLoaded }: { fontsLoaded: boolean }) {
  const { isLoading, user } = useAuth();
  const ready = fontsLoaded && !isLoading;

  useEffect(() => {
    if (ready) SplashScreen.hideAsync();
  }, [ready]);

  if (!ready) return null;

  // The web uses the site header instead of native navigation bars on public pages.
  const nativeHeader = Platform.OS !== 'web';
  const afterSignIn = user?.is_email_verified ? '/shops' : '/verify-email';

  return (
    <Stack
      screenOptions={{
        headerBackButtonDisplayMode: 'minimal',
        headerShadowVisible: false,
        headerTitleStyle: { fontFamily: Fonts.displayMedium },
      }}>
      {/* The landing page is the home page for everyone; signed-in users reach their shops from its menu. */}
      <Stack.Screen name="index" options={{ headerShown: false, title: 'Sklep internetowy w dwie minuty' }} />
      <Stack.Protected guard={!user} redirectTo={afterSignIn}>
        <Stack.Screen name="sign-in" options={{ headerShown: false, title: 'Logowanie' }} />
        <Stack.Screen name="sign-up" options={{ headerShown: false, title: 'Załóż konto' }} />
        <Stack.Screen name="reset-password" options={{ headerShown: false, title: 'Nowe hasło' }} />
      </Stack.Protected>
      <Stack.Protected guard={!!user && !user.is_email_verified} redirectTo={user ? '/shops' : '/'}>
        <Stack.Screen name="verify-email" options={{ headerShown: false, title: 'Potwierdź e-mail' }} />
      </Stack.Protected>
      <Stack.Protected guard={!!user?.is_email_verified} redirectTo={user ? '/verify-email' : '/'}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="shops/new" options={{ title: 'Nowy sklep', presentation: 'modal' }} />
        <Stack.Screen name="shops/[id]" options={{ title: 'Sklep' }} />
        <Stack.Screen name="shops/[id]/settings" options={{ title: 'Ustawienia sklepu' }} />
        <Stack.Screen name="shops/[id]/sales" options={{ title: 'Sprzedaż' }} />
        <Stack.Screen name="billing/index" options={{ title: 'Plan i płatności' }} />
        <Stack.Screen name="billing/checkout" options={{ title: 'Wybierz plan' }} />
        <Stack.Screen name="billing/change" options={{ title: 'Zmień plan' }} />
        <Stack.Screen name="billing/return" options={{ title: 'Płatność' }} />
        <Stack.Screen name="delete-account" options={{ title: 'Usuń konto' }} />
      </Stack.Protected>
      <Stack.Screen name="about" options={{ title: 'Jak to działa', headerShown: nativeHeader }} />
      <Stack.Screen name="contact" options={{ title: 'Kontakt', headerShown: nativeHeader }} />
      <Stack.Screen name="pricing" options={{ title: 'Cennik', headerShown: nativeHeader }} />
    </Stack>
  );
}
