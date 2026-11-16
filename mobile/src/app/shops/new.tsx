import { Link, router } from 'expo-router';
import { useEffect, useState, type ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Switch, View } from 'react-native';

import { isShopLimitReached, paidShopCount, shopLimitMessage } from '@/components/new-shop-button';
import { Page } from '@/components/page';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { ChipSelect } from '@/components/ui/chip-select';
import { TextField } from '@/components/ui/text-field';
import { Themes } from '@/constants/content';
import { Fonts, Radius, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api, ApiError } from '@/lib/api';
import { plural } from '@/lib/plural';
import { slugify } from '@/lib/slugify';
import type { FormOptions, NewShop, Shop, ShopDetail } from '@/lib/types';

type SlugCheck = { slug: string; available: boolean; reason: string | null };

export default function NewShopScreen() {
  const { user } = useAuth();
  const { data: options, error } = useApiQuery<FormOptions>('/shops/form-options/');
  const { data: shops, error: shopsError } = useApiQuery<Shop[]>('/shops/');

  // The form is also reachable by URL, so check the limit here and not only on the buttons.
  if (user && !user.plan) return <PlanRequired />;
  if (user && isShopLimitReached(user.shop_limit, paidShopCount(shops)))
    return <LimitReached limit={user.shop_limit} />;
  if (options && (shops || shopsError)) return <NewShopForm options={options} />;
  return (
    <Page>
      {error ? (
        <ThemedText themeColor="danger">{error.message}</ThemedText>
      ) : (
        <ActivityIndicator style={styles.loader} />
      )}
    </Page>
  );
}

function PlanRequired() {
  const theme = useTheme();
  return (
    <Page maxWidth={760}>
      <View style={[styles.limit, { backgroundColor: theme.surface, borderColor: theme.border }]}>
        <ThemedText type="title">Najpierw wybierz plan</ThemedText>
        <ThemedText themeColor="textSecondary">
          Sklepy zakładasz w ramach planu. Wybierz go i zapłać kartą, a od razu wrócisz do zakładania sklepu.
        </ThemedText>
        <Link href="/billing/checkout" asChild>
          <Button title="Wybierz plan" icon="card" style={styles.limitButton} />
        </Link>
      </View>
    </Page>
  );
}

function LimitReached({ limit }: { limit: number }) {
  const theme = useTheme();
  return (
    <Page maxWidth={760}>
      <View style={[styles.limit, { backgroundColor: theme.surface, borderColor: theme.border }]}>
        <ThemedText type="title">
          Masz już {limit} {plural(limit, ['sklep', 'sklepy', 'sklepów'])}
        </ThemedText>
        <ThemedText themeColor="textSecondary">{shopLimitMessage(limit)}</ThemedText>
        <Button
          title="Wróć do sklepów"
          variant="secondary"
          onPress={() => (router.canGoBack() ? router.back() : router.replace('/shops'))}
          style={styles.limitButton}
        />
      </View>
    </Page>
  );
}

function NewShopForm({ options }: { options: FormOptions }) {
  const theme = useTheme();
  const notify = useNotify();
  const [form, setForm] = useState<NewShop>(() => ({
    name: '',
    slug: '',
    platform: options.platforms[0].value,
    industry: '',
    template: options.templates.find((t) => t.platform === options.platforms[0].value)?.slug ?? '',
    category_count: options.category_count.default,
    language: options.languages[0].value,
    currency: options.currencies[0].value,
    country: options.countries[0].value,
    include_sample_products: true,
  }));
  const [slugEdited, setSlugEdited] = useState(false);
  const [lastSlugCheck, setLastSlugCheck] = useState<SlugCheck | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
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
    try {
      const shop = await api<ShopDetail>('/shops/', { method: 'POST', body: form });
      notify.success(`Zakładamy sklep „${shop.name}”. To potrwa około dwóch minut.`);
      router.back();
      router.push({ pathname: '/shops/[id]', params: { id: shop.id } });
    } catch (e) {
      // Field messages sit under the fields; the bar also covers fields scrolled out of view.
      if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
      notify.error((e as Error).message);
      setSubmitting(false);
    }
  }

  function choosePlatform(platform: NewShop['platform']) {
    if (platform === form.platform) return;
    // Each platform has its own themes.
    setForm((current) => ({
      ...current,
      platform,
      template: options.templates.find((t) => t.platform === platform)?.slug ?? '',
    }));
    setFieldErrors(({ platform: _, template: __, ...rest }) => rest);
  }

  const templates = options.templates.filter((t) => t.platform === form.platform);
  const { min, max } = options.category_count;
  const slugError =
    fieldErrors.slug ?? (slugCheck && !slugCheck.available ? (slugCheck.reason ?? undefined) : undefined);
  const address = `${form.slug || 'twoj-sklep'}.${options.base_domain}`;

  return (
    <Page maxWidth={760}>
      <View style={styles.intro}>
        <ThemedText type="title">Opisz swój sklep</ThemedText>
        <ThemedText themeColor="textSecondary">
          Wszystko poza nazwą i adresem zmienisz później w ustawieniach sklepu.
        </ThemedText>
      </View>

      <Section title="Nazwa i adres">
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
          autoCapitalize="none"
          autoCorrect={false}
        />
        <View style={[styles.address, { backgroundColor: theme.surfaceMuted }]}>
          <ThemedText type="small" themeColor="textSecondary">
            Klienci wejdą do sklepu pod adresem
          </ThemedText>
          <ThemedText style={styles.addressText}>{address}</ThemedText>
          {slugCheck?.available ? (
            <ThemedText type="smallBold" themeColor="success">
              ✓ Adres jest wolny
            </ThemedText>
          ) : null}
        </View>
      </Section>

      <Section title="Branża" text="Na jej podstawie przygotujemy nazwy kategorii.">
        <ChipSelect
          label="Czym handlujesz?"
          options={options.industries}
          value={form.industry}
          onChange={(value) => update('industry', value)}
          error={fieldErrors.industry}
        />
      </Section>

      <Section title="System sklepu" text="Na nim będzie działał sklep i jego panel. Później go nie zmienisz.">
        <View style={styles.templates} accessibilityRole="radiogroup">
          {options.platforms.map((platform) => (
            <Choice
              key={platform.value}
              title={platform.label}
              text={platform.description}
              selected={platform.value === form.platform}
              onPress={() => choosePlatform(platform.value)}
            />
          ))}
        </View>
        {fieldErrors.platform ? <ThemedText themeColor="danger">{fieldErrors.platform}</ThemedText> : null}
      </Section>

      <Section title="Wygląd">
        <View style={styles.templates} accessibilityRole="radiogroup">
          {templates.map((template) => {
            const colors = Themes.find((t) => t.name === template.name)?.colors ?? [];
            return (
              <Choice
                key={template.slug}
                title={template.name}
                text={template.description}
                colors={colors}
                selected={template.slug === form.template}
                onPress={() => update('template', template.slug)}
              />
            );
          })}
        </View>
        {fieldErrors.template ? <ThemedText themeColor="danger">{fieldErrors.template}</ThemedText> : null}
      </Section>

      <Section title="Asortyment">
        <View style={styles.row}>
          <View style={styles.flex}>
            <ThemedText type="smallBold">Liczba kategorii produktów</ThemedText>
            <ThemedText type="small" themeColor="textSecondary">
              Od {min} do {max}. Dodasz i usuniesz je później.
            </ThemedText>
          </View>
          <View style={styles.stepper}>
            <StepperButton
              label="−"
              disabled={form.category_count <= min}
              onPress={() => update('category_count', form.category_count - 1)}
            />
            <ThemedText type="subtitle" style={styles.stepperValue}>
              {form.category_count}
            </ThemedText>
            <StepperButton
              label="+"
              disabled={form.category_count >= max}
              onPress={() => update('category_count', form.category_count + 1)}
            />
          </View>
        </View>
        <View style={styles.row}>
          <View style={styles.flex}>
            <ThemedText type="smallBold">Przykładowe produkty</ThemedText>
            <ThemedText type="small" themeColor="textSecondary">
              Sześć produktów, żeby sklep nie był pusty. Usuniesz je jednym kliknięciem.
            </ThemedText>
          </View>
          <Switch
            value={form.include_sample_products}
            onValueChange={(v) => update('include_sample_products', v)}
            trackColor={{ true: theme.primary, false: theme.border }}
          />
        </View>
      </Section>

      <Section title="Region">
        <ChipSelect
          label="Język sklepu"
          options={options.languages}
          value={form.language}
          onChange={(v) => update('language', v)}
        />
        <ChipSelect
          label="Waluta"
          options={options.currencies}
          value={form.currency}
          onChange={(v) => update('currency', v)}
        />
        <ChipSelect
          label="Kraj"
          options={options.countries}
          value={form.country}
          onChange={(v) => update('country', v)}
        />
      </Section>

      <Button
        title="Załóż sklep"
        size="large"
        onPress={handleSubmit}
        loading={submitting}
        disabled={!form.name || !form.slug || !form.industry || !form.template}
      />
    </Page>
  );
}

function Section({ title, text, children }: { title: string; text?: string; children: ReactNode }) {
  const theme = useTheme();
  return (
    <View style={[styles.section, { borderTopColor: theme.border }]}>
      <View style={styles.sectionHead}>
        <ThemedText type="subtitle">{title}</ThemedText>
        {text ? (
          <ThemedText type="small" themeColor="textSecondary">
            {text}
          </ThemedText>
        ) : null}
      </View>
      {children}
    </View>
  );
}

function Choice({
  title,
  text,
  colors = [],
  selected,
  onPress,
}: {
  title: string;
  text: string;
  colors?: string[];
  selected: boolean;
  onPress: () => void;
}) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[
        styles.template,
        {
          backgroundColor: selected ? theme.primaryMuted : theme.surface,
          borderColor: selected ? theme.primary : theme.border,
        },
      ]}>
      {colors.length ? (
        <View style={styles.swatches}>
          {colors.map((color) => (
            <View key={color} style={[styles.swatch, { backgroundColor: color }]} />
          ))}
        </View>
      ) : null}
      <ThemedText type="heading">{title}</ThemedText>
      <ThemedText type="small" themeColor="textSecondary">
        {text}
      </ThemedText>
    </Pressable>
  );
}

function StepperButton({ label, disabled, onPress }: { label: string; disabled: boolean; onPress: () => void }) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label === '+' ? 'Więcej kategorii' : 'Mniej kategorii'}
      onPress={onPress}
      disabled={disabled}
      style={[
        styles.stepperButton,
        { borderColor: theme.border, backgroundColor: theme.surface, opacity: disabled ? 0.4 : 1 },
      ]}>
      <ThemedText type="subtitle">{label}</ThemedText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  loader: {
    marginVertical: Spacing.six,
  },
  limit: {
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  limitButton: {
    alignSelf: 'flex-start',
  },
  intro: {
    gap: Spacing.one,
  },
  section: {
    gap: Spacing.three,
    paddingTop: Spacing.four,
    borderTopWidth: 1,
  },
  sectionHead: {
    gap: Spacing.half,
  },
  address: {
    gap: Spacing.half,
    padding: Spacing.three,
    borderRadius: Radius.medium,
  },
  addressText: {
    fontFamily: Fonts.mono,
    fontSize: 15,
  },
  templates: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
  template: {
    flexBasis: 200,
    flexGrow: 1,
    gap: Spacing.one + Spacing.half,
    padding: Spacing.three,
    borderRadius: Radius.medium,
    borderWidth: 1.5,
  },
  swatches: {
    flexDirection: 'row',
    gap: Spacing.one,
    marginBottom: Spacing.one,
  },
  swatch: {
    width: 22,
    height: 22,
    borderRadius: 6,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
  },
  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  stepperButton: {
    width: 44,
    height: 44,
    borderRadius: Radius.pill,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepperValue: {
    minWidth: 40,
    textAlign: 'center',
  },
});
