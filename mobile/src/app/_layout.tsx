import { BricolageGrotesque_600SemiBold, BricolageGrotesque_700Bold } from '@expo-google-fonts/bricolage-grotesque';
import {
  Figtree_400Regular,
  Figtree_500Medium,
  Figtree_600SemiBold,
  Figtree_700Bold,
} from '@expo-google-fonts/figtree';
import { FontDisplay, useFonts, type FontSource } from 'expo-font';
import { DarkTheme, DefaultTheme, type Href, router, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { AppState, Platform, useColorScheme } from 'react-native';

import { Colors, Fonts } from '@/constants/theme';
import { AuthProvider, useAuth } from '@/context/auth';
import { NotificationsProvider } from '@/context/notifications';
import { configurePush, onPushTokenChange, openTappedNotifications, registerDevice } from '@/lib/push';

SplashScreen.preventAutoHideAsync();
configurePush();

// The web shows the page at once in a system font (see `Fonts`) and swaps these in when they arrive. On a phone
// they are files in the app, loaded while the splash screen is up.
const font = (source: number): FontSource => ({ uri: source, display: FontDisplay.SWAP });
const waitForFonts = Platform.OS !== 'web';

export default function RootLayout() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const [fontsLoaded, fontsError] = useFonts({
    BricolageGrotesque_600SemiBold: font(BricolageGrotesque_600SemiBold),
    BricolageGrotesque_700Bold: font(BricolageGrotesque_700Bold),
    Figtree_400Regular: font(Figtree_400Regular),
    Figtree_500Medium: font(Figtree_500Medium),
    Figtree_600SemiBold: font(Figtree_600SemiBold),
    Figtree_700Bold: font(Figtree_700Bold),
  });
  // Fonts that failed to load leave the system font instead of the splash screen for good.
  const fontsReady = !waitForFonts || fontsLoaded || !!fontsError;
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
          <RootNavigator fontsReady={fontsReady} />
        </AuthProvider>
      </NotificationsProvider>
    </ThemeProvider>
  );
}

function RootNavigator({ fontsReady }: { fontsReady: boolean }) {
  // Without a saved session the account check needs no request, so visitors don't wait for it.
  const { isLoading, user } = useAuth();
  const ready = fontsReady && !isLoading;
  const signedIn = ready && !!user?.is_email_verified;

  useEffect(() => {
    if (ready) SplashScreen.hideAsync();
  }, [ready]);

  usePushNotifications(signedIn ? user.id : null);

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
        <Stack.Screen name="notifications" options={{ title: 'Powiadomienia' }} />
      </Stack.Protected>
      <Stack.Screen name="about" options={{ title: 'Jak to działa', headerShown: nativeHeader }} />
      <Stack.Screen name="contact" options={{ title: 'Kontakt', headerShown: nativeHeader }} />
      <Stack.Screen name="pricing" options={{ title: 'Cennik', headerShown: nativeHeader }} />
    </Stack>
  );
}


/**
 * For a signed-in user: sends the phone's push token to the platform (when notifications are allowed) on start,
 * on coming back to the app and when the token changes, and opens the screen of a tapped notification.
 */
function usePushNotifications(userId: number | null) {
  useEffect(() => {
    if (userId === null) return;
    const register = (force: boolean) => registerDevice({ force }).catch(() => {});
    register(true);
    const appState = AppState.addEventListener('change', (state) => {
      if (state === 'active') register(false);
    });
    const stopTokens = onPushTokenChange(() => register(true));
    const stopTaps = openTappedNotifications((url) => router.push(url as Href));
    return () => {
      appState.remove();
      stopTokens();
      stopTaps();
    };
  }, [userId]);
}

