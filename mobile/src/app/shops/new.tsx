import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Switch, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { ChipSelect } from '@/components/ui/chip-select';
import { TextField } from '@/components/ui/text-field';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api, ApiError } from '@/lib/api';
import { slugify } from '@/lib/slugify';
import type { FormOptions, NewShop, ShopDetail } from '@/lib/types';

type SlugCheck = { slug: string; available: boolean; reason: string | null };

export default function NewShopScreen() {
  const { data: options, error } = useApiQuery<FormOptions>('/shops/form-options/');

  if (options) return <NewShopForm options={options} />;
  return error ? (
    <ThemedText themeColor="danger" style={styles.content}>
      {error.message}
    </ThemedText>
  ) : (
    <ActivityIndicator style={styles.loader} />
  );
}

function NewShopForm({ options }: { options: FormOptions }) {
  const theme = useTheme();
  const [form, setForm] = useState<NewShop>(() => ({
    name: '',
    slug: '',
    industry: '',
    template: options.templates[0]?.slug ?? '',
    category_count: options.category_count.default,
    language: options.languages[0].value,
    currency: options.currencies[0].value,
    country: options.countries[0].value,
    include_sample_products: true,
  }));
  const [slugEdited, setSlugEdited] = useState(false);
  const [lastSlugCheck, setLastSlugCheck] = useState<SlugCheck | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);

  const slug = form.slug;
  // A check is only meaningful for the slug currently typed in.
  const slugCheck = lastSlugCheck?.slug === slug ? lastSlugCheck : null;
  useEffect(() => {
    if (slug.length < 3) return;
    const timer = setTimeout(async () => {
      try {
        setLastSlugCheck(await api<SlugCheck>(`/shops/check-slug/?slug=${encodeURIComponent(slug)}`));
      } catch {
        // The server validates the slug again on submit.
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [slug]);

  function update<K extends keyof NewShop>(key: K, value: NewShop[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setFieldErrors(({ [key]: _, ...rest }) => rest);
  }

  async function handleSubmit() {
    setSubmitting(true);
    setError(undefined);
    try {
      const shop = await api<ShopDetail>('/shops/', { method: 'POST', body: form });
      router.back();
      router.push({ pathname: '/shops/[id]', params: { id: shop.id } });
    } catch (e) {
      if (e instanceof ApiError && Object.keys(e.fieldErrors).length) setFieldErrors(e.fieldErrors);
      else setError((e as Error).message);
      setSubmitting(false);
    }
  }

  const { min, max } = options.category_count;
  const slugError = fieldErrors.slug ?? (slugCheck && !slugCheck.available ? slugCheck.reason ?? undefined : undefined);
  const selectedTemplate = options.templates.find((t) => t.slug === form.template);

  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic"
      keyboardShouldPersistTaps="handled"
      automaticallyAdjustKeyboardInsets>
      <TextField
        label="Nazwa sklepu"
        value={form.name}
        onChangeText={(name) => {
          update('name', name);
          if (!slugEdited) update('slug', slugify(name));
        }}
        error={fieldErrors.name}
        placeholder="np. Pracownia Ceramiki"
      />
      <TextField
        label="Adres sklepu"
        value={form.slug}
        onChangeText={(text) => {
          setSlugEdited(true);
          update('slug', text.toLowerCase());
        }}
        error={slugError}
        hint={slugCheck?.available ? `✓ ${form.slug}.${options.base_domain} jest wolny` : `${form.slug || 'adres'}.${options.base_domain}`}
        autoCapitalize="none"
        autoCorrect={false}
      />

      <ChipSelect
        label="Branża"
        options={options.industries}
        value={form.industry}
        onChange={(value) => update('industry', value)}
        error={fieldErrors.industry}
      />

      <ChipSelect
        label="Szablon"
        options={options.templates.map((t) => ({ value: t.slug, label: t.name }))}
        value={form.template}
        onChange={(value) => update('template', value)}
        error={fieldErrors.template}
      />
      {selectedTemplate ? (
        <ThemedText type="small" themeColor="textSecondary">
          {selectedTemplate.description}
        </ThemedText>
      ) : null}

      <View style={styles.field}>
        <ThemedText type="smallBold">Liczba kategorii produktów</ThemedText>
        <View style={styles.stepper}>
          <StepperButton label="−" disabled={form.category_count <= min} onPress={() => update('category_count', form.category_count - 1)} />
          <ThemedText type="subtitle" style={styles.stepperValue}>
            {form.category_count}
          </ThemedText>
          <StepperButton label="+" disabled={form.category_count >= max} onPress={() => update('category_count', form.category_count + 1)} />
        </View>
      </View>

      <ChipSelect label="Język sklepu" options={options.languages} value={form.language} onChange={(v) => update('language', v)} />
      <ChipSelect label="Waluta" options={options.currencies} value={form.currency} onChange={(v) => update('currency', v)} />
      <ChipSelect label="Kraj" options={options.countries} value={form.country} onChange={(v) => update('country', v)} />

      <View style={styles.switchRow}>
        <View style={styles.flex}>
          <ThemedText type="smallBold">Przykładowe produkty</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            Dodamy kilka produktów, żeby sklep nie był pusty.
          </ThemedText>
        </View>
        <Switch value={form.include_sample_products} onValueChange={(v) => update('include_sample_products', v)} />
      </View>

      {error ? <ThemedText themeColor="danger">{error}</ThemedText> : null}
      <Button
        title="Załóż sklep"
        onPress={handleSubmit}
        loading={submitting}
        disabled={!form.name || !form.slug || !form.industry || !form.template}
      />
    </ScrollView>
  );
}

function StepperButton({ label, disabled, onPress }: { label: string; disabled: boolean; onPress: () => void }) {
  const theme = useTheme();
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={[styles.stepperButton, { backgroundColor: theme.backgroundElement, opacity: disabled ? 0.4 : 1 }]}>
      <ThemedText type="subtitle">{label}</ThemedText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  loader: {
    flex: 1,
  },
  content: {
    gap: Spacing.four,
    padding: Spacing.four,
    paddingBottom: Spacing.six,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
  field: {
    gap: Spacing.two,
  },
  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
  },
  stepperButton: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepperValue: {
    minWidth: 48,
    textAlign: 'center',
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
  },
});
