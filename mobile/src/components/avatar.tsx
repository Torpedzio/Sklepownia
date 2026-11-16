import { Image } from 'expo-image';
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Fonts } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { User } from '@/lib/types';

/** The user's profile picture, or the first letter of their name on a coloured circle. */
export function Avatar({
  user,
  size = 80,
}: {
  user: Pick<User, 'first_name' | 'email' | 'avatar_url'>;
  size?: number;
}) {
  const theme = useTheme();
  const circle = { width: size, height: size, borderRadius: size / 2 };
  if (user.avatar_url) {
    return (
      <Image
        source={user.avatar_url}
        style={[circle, { backgroundColor: theme.surfaceMuted }]}
        contentFit="cover"
        transition={150}
        accessibilityLabel="Zdjęcie profilowe"
      />
    );
  }
  const initial = (user.first_name || user.email).charAt(0).toUpperCase();
  return (
    <View style={[styles.initial, circle, { backgroundColor: theme.primary }]}>
      <ThemedText style={[styles.letter, { color: theme.onPrimary, fontSize: size * 0.45, lineHeight: size * 0.55 }]}>
        {initial}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  initial: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  letter: {
    fontFamily: Fonts.display,
  },
});
