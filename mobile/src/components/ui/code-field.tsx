import { StyleSheet } from 'react-native';

import { TextField } from '@/components/ui/text-field';
import { Fonts } from '@/constants/theme';

type CodeFieldProps = {
  value: string;
  onChangeText: (code: string) => void;
  onSubmitEditing?: () => void;
  error?: string;
};

/** The 6-digit e-mailed code: other characters dropped, filled in from the message on phones. */
export function CodeField({ value, onChangeText, onSubmitEditing, error }: CodeFieldProps) {
  return (
    <TextField
      label="Kod z wiadomości"
      value={value}
      onChangeText={(text) => onChangeText(text.replace(/\D/g, '').slice(0, CODE_LENGTH))}
      error={error}
      keyboardType="number-pad"
      autoComplete="one-time-code"
      textContentType="oneTimeCode"
      maxLength={CODE_LENGTH}
      style={styles.code}
      onSubmitEditing={onSubmitEditing}
    />
  );
}

export const CODE_LENGTH = 6;

const styles = StyleSheet.create({
  code: {
    fontFamily: Fonts.displayMedium,
    fontSize: 30,
    letterSpacing: 10,
    textAlign: 'center',
    minHeight: 64,
  },
});
