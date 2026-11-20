import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Choice } from '@/lib/types';

type ChipSelectProps = {
  label: string;
  options: Choice[];
  value: string;
  onChange: (value: string) => void;
  error?: string;
};

export function ChipSelect({ label, options, value, onChange, error }: ChipSelectProps) {
  return (
    <View style={styles.container}>
      <ThemedText type="smallBold">{label}</ThemedText>
      <View style={styles.chips} accessibilityRole="radiogroup">
        {options.map((option) => (
          <Chip
            key={option.value}
            label={option.label}
            role="radio"
            selected={option.value === value}
            onPress={() => onChange(option.value)}
          />
        ))}
      </View>
      <FieldError error={error} />
    </View>
  );
}

type ChipMultiSelectProps = {
  label: string;
  options: Choice[];
  values: string[];
  /** In the order they were chosen. */
  onChange: (values: string[]) => void;
  hint?: string;
  error?: string;
};

/** Any number of the options, each chip toggled on its own. */
export function ChipMultiSelect({ label, options, values, onChange, hint, error }: ChipMultiSelectProps) {
  return (
    <View style={styles.container}>
      <ThemedText type="smallBold">{label}</ThemedText>
      <View style={styles.chips}>
        {options.map((option) => {
          const selected = values.includes(option.value);
          return (
            <Chip
              key={option.value}
              label={option.label}
              role="checkbox"
              selected={selected}
              onPress={() =>
                onChange(selected ? values.filter((value) => value !== option.value) : [...values, option.value])
              }
            />
          );
        })}
      </View>
      {hint ? (
        <ThemedText type="small" themeColor="textSecondary">
          {hint}
        </ThemedText>
      ) : null}
      <FieldError error={error} />
    </View>
  );
}

function Chip({
  label,
  role,
  selected,
  onPress,
}: {
  label: string;
  role: 'radio' | 'checkbox';
  selected: boolean;
  onPress: () => void;
}) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole={role}
      accessibilityState={role === 'radio' ? { selected } : { checked: selected }}
      onPress={onPress}
      style={[
        styles.chip,
        {
          backgroundColor: selected ? theme.primaryMuted : theme.surface,
          borderColor: selected ? theme.primary : theme.border,
        },
      ]}>
      <ThemedText type={selected ? 'smallBold' : 'small'} themeColor={selected ? 'primary' : 'text'}>
        {label}
      </ThemedText>
    </Pressable>
  );
}

function FieldError({ error }: { error?: string }) {
  return error ? (
    <ThemedText type="small" themeColor="danger">
      {error}
    </ThemedText>
  ) : null;
}

const styles = StyleSheet.create({
  container: {
    gap: Spacing.two,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
  },
  chip: {
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: Radius.pill,
    borderWidth: 1.5,
  },
});
