import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, useWindowDimensions, View } from 'react-native';

import { backArrowOptions } from '@/components/back-link';
import { Icon } from '@/components/icon';
import { Page } from '@/components/page';
import { SettingsMenu, SettingsPane, type SettingsMenuItem } from '@/components/settings-menu';
import { SettingsSection } from '@/components/settings-section';
import { supports } from '@/components/shop-overview';
import { ShopLoginSteps } from '@/components/shop-login-guide';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { ChipSelect } from '@/components/ui/chip-select';
import { SwitchRow } from '@/components/ui/switch-row';
import { TextField } from '@/components/ui/text-field';
import { Radius, Spacing, WideBreakpoint } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api, ApiError } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import { changedFields, type Drafts, type FieldErrors, formatTime, sectionErrors, toApi } from '@/lib/settings-form';
import type { SettingsSection as Section, ShopOperation, ShopSettings, ShopSettingsValues } from '@/lib/types';

// Read the shop again on opening when the last read is older than this.
const FRESH_FOR_MS = 60_000;
const POLL_MS = 1500;
const HISTORY_LENGTH = 10;
// These take about a minute and change how the shop looks, so they're confirmed first.
const SLOW_SECTIONS: Partial<Record<Section, string>> = {
  region: 'Zmiana języka, waluty albo kraju potrwa około minuty.',
  appearance: 'Zmiana motywu potrwa do minuty i zmieni układ stron sklepu.',
};

type MenuKey = Section | 'security' | 'manual' | 'history';

// Menu order; `slug` is what the address shows (?section=platnosci).
const MENU: (SettingsMenuItem<MenuKey> & { slug: string })[] = [
  { key: 'general', slug: 'podstawowe', title: 'Podstawowe', icon: 'store' },
  { key: 'availability', slug: 'dostepnosc', title: 'Sklep otwarty', icon: 'power' },
  { key: 'shopping', slug: 'zakupy', title: 'Zakupy', icon: 'cart' },
  { key: 'payments', slug: 'platnosci', title: 'Płatności', icon: 'card' },
  { key: 'shipping', slug: 'wysylka', title: 'Wysyłka', icon: 'truck' },
  { key: 'taxes', slug: 'podatki', title: 'Podatki', icon: 'percent' },
  { key: 'region', slug: 'region', title: 'Region', icon: 'globe' },
  { key: 'appearance', slug: 'wyglad', title: 'Wygląd', icon: 'palette' },
  { key: 'security', slug: 'bezpieczenstwo', title: 'Bezpieczeństwo', icon: 'shield' },
  { key: 'manual', slug: 'reczne', title: 'Ustawienia ręczne', icon: 'admin' },
  { key: 'history', slug: 'historia', title: 'Ostatnie zmiany', icon: 'history' },
];

const SECTION_KEYS: MenuKey[] = ['general', 'availability', 'shopping', 'payments', 'shipping', 'taxes', 'region', 'appearance'];

/** "panel WordPressa" → "panelu WordPressa", for "w …". */
function panelLocative(panelName: string | undefined) {
  return (panelName ?? 'panel sklepu').replace(/^panel\b/, 'panelu');
}

/** The menu without the sections the shop's platform doesn't let the app change. */
function menuFor(settings: ShopSettings | undefined) {
  if (!settings) return MENU;
  return MENU.filter((item) => !SECTION_KEYS.includes(item.key) || supports(settings, item.key as Section));
}

export default function ShopSettingsScreen() {
  const { id, section: sectionSlug } = useLocalSearchParams<{ id: string; section?: string }>();
  const { width } = useWindowDimensions();
  const wide = width >= WideBreakpoint;
  const notify = useNotify();
  const {
    data: settings,
    error,
    refresh,
  } = useApiQuery<ShopSettings>(`/shops/${id}/settings/`, {
    refetchInterval: (data) => (data?.busy ? POLL_MS : false),
  });
  const menu = menuFor(settings);
  const active = (menu.find((item) => item.slug === sectionSlug) ?? menu[0]).key;
  const select = (key: MenuKey) => router.setParams({ section: MENU.find((item) => item.key === key)!.slug });
  const { data: history, refresh: refreshHistory } = useApiQuery<ShopOperation[]>(`/shops/${id}/operations/`);
  const [drafts, setDrafts] = useState<Drafts>({});
  const [errors, setErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState<Section | 'security' | null>(null);
  // The operation whose end this screen reports; operations finished before it opened stay quiet.
  const [watched, setWatched] = useState<number | null>(null);
  const announced = useRef(new Set<number>());
  // A change still running when the screen opens (e.g. after leaving it mid-save) is reported too.
  const [adopted, setAdopted] = useState(false);
  if (settings && !adopted) {
    setAdopted(true);
    if (settings.busy && settings.operation) setWatched(settings.operation.id);
  }

  // Read the settings from the shop once on opening, so changes made in its panel show up.
  const readOnOpen = useRef(false);
  useEffect(() => {
    if (!settings || readOnOpen.current) return;
    readOnOpen.current = true;
    if (settings.busy) return;
    const age = settings.synced_at ? Date.now() - new Date(settings.synced_at).getTime() : Infinity;
    if (age < FRESH_FOR_MS) return;
    api<ShopSettings>(`/shops/${id}/settings/refresh/`, { method: 'POST' })
      .then(refresh)
      .catch(() => {});
  }, [settings, id, refresh]);

  const operation = settings?.operation;
  // Once a change is in the shop, its edits are the saved values, so they stop being drafts.
  const operationState = operation ? `${operation.id}:${operation.status}` : '';
  const [seenOperationState, setSeenOperationState] = useState(operationState);
  if (operationState !== seenOperationState) {
    setSeenOperationState(operationState);
    if (operation?.status === 'succeeded') {
      const sections = Object.keys(operation.changes);
      setDrafts(Object.fromEntries(Object.entries(drafts).filter(([key]) => !sections.includes(key))));
    }
  }

  useEffect(() => {
    if (!operation || operation.id !== watched || !['succeeded', 'failed'].includes(operation.status)) return;
    if (announced.current.has(operation.id)) return;
    announced.current.add(operation.id);
    refreshHistory();
    if (operation.status === 'failed') {
      notify.error(operation.error || 'Nie udało się wprowadzić zmian w sklepie.');
      return;
    }
    if (operation.kind === 'update_settings') {
      notify.success(`Zapisano w sklepie: ${operation.changed_fields.join(', ').toLowerCase()}.`);
    } else if (operation.kind === 'reset_admin_password') {
      notify.success('Nowe hasło administratora wysłaliśmy na Twój adres e-mail.');
    } else if (operation.kind === 'remove_sample_products') {
      const removed = operation.result.removed ?? 0;
      notify.success(
        removed ? `Usunięto przykładowe produkty (${removed}).` : 'W sklepie nie było przykładowych produktów.',
      );
    }
  }, [operation, watched, notify, refreshHistory]);

  if (!settings) {
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

  const values = settings.values;
  const options = settings.options;
  const busy = settings.busy;

  function get<S extends Section, K extends keyof ShopSettingsValues[S] & string>(section: S, key: K) {
    const draft = drafts[section]?.[key];
    return (draft ?? values[section][key]) as ShopSettingsValues[S][K];
  }

  function set(section: Section, key: string, value: string | boolean) {
    setDrafts((current) => ({ ...current, [section]: { ...current[section], [key]: value } }));
    setErrors((current) => ({ ...current, [section]: { ...current[section], [key]: '' } }));
  }

  function changes(section: Section) {
    return changedFields(values[section] as Record<string, unknown>, drafts[section]);
  }

  function undo(section: Section) {
    setDrafts((current) => ({ ...current, [section]: {} }));
    setErrors((current) => ({ ...current, [section]: {} }));
  }

  async function save(section: Section) {
    const slow = SLOW_SECTIONS[section];
    if (
      slow &&
      !(await confirm('Zapisać zmiany?', `${slow} W tym czasie sklep może przez chwilę wyglądać inaczej.`, 'Zapisz'))
    ) {
      return;
    }
    const body = Object.fromEntries(Object.entries(changes(section)).map(([key, value]) => [key, toApi(key, value)]));
    setSaving(section);
    try {
      const next = await api<ShopSettings>(`/shops/${id}/settings/`, { method: 'PATCH', body: { [section]: body } });
      setErrors((current) => ({ ...current, [section]: {} }));
      if (next.busy && next.operation) {
        setWatched(next.operation.id);
      } else {
        undo(section);
        notify.success('Sklep ma już te ustawienia.');
      }
      await refresh();
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) {
        setErrors(sectionErrors(e.data));
        notify.error('Popraw zaznaczone pola.');
      } else {
        notify.error((e as Error).message);
      }
    } finally {
      setSaving(null);
    }
  }

  async function runOperation(path: string, title: string, message: string, confirmLabel: string) {
    if (!(await confirm(title, message, confirmLabel))) return;
    setSaving('security');
    try {
      const started = await api<ShopOperation>(`/shops/${id}/${path}/`, { method: 'POST' });
      setWatched(started.id);
      await refresh();
    } catch (e) {
      notify.error((e as Error).message);
    } finally {
      setSaving(null);
    }
  }

  const section = (key: Section) => ({
    dirty: Object.keys(changes(key)).length > 0,
    saving: saving === key,
    waiting: busy,
    onSave: () => save(key),
    onUndo: () => undo(key),
  });
  const fieldError = (key: Section, field: string) => errors[key]?.[field] || undefined;
  const currency = get('region', 'currency');
  const country = get('region', 'country');
  const rates = options.vat_rates[country] ?? ['0.00'];
  const rate = get('taxes', 'standard_rate');
  const rateChoices = [...new Set([...rates, values.taxes.standard_rate])].map((value) => ({
    value,
    label: `${Number(value)}%`,
  }));

  return (
    <Page maxWidth={1040}>
      <Stack.Screen options={{ title: 'Ustawienia sklepu', ...backArrowOptions(`/shops/${id}`, 'Wróć do sklepu') }} />

      <View style={styles.header}>
        <ThemedText type="title">Ustawienia sklepu</ThemedText>
        <ThemedText themeColor="textSecondary">
          Zmiany zapisujemy prosto w sklepie „{values.general.name}”, a zmiany zrobione w panelu sklepu też tu
          zobaczysz. Każdą sekcję zapisujesz osobno.
        </ThemedText>
      </View>

      <StatusBar
        settings={settings}
        onRefresh={() => {
          api(`/shops/${id}/settings/refresh/`, { method: 'POST' })
            .then(refresh)
            .catch((e: Error) => notify.error(e.message));
        }}
      />

      <View style={[styles.layout, wide && styles.layoutWide]}>
        <View style={wide && styles.menu}>
          <SettingsMenu
            items={menu.map((item) => ({
              ...item,
              dirty: item.key in values && Object.keys(changes(item.key as Section)).length > 0,
            }))}
            active={active}
            onSelect={select}
            vertical={wide}
          />
        </View>
        <View style={[styles.content, wide && styles.flex]}>
          <SettingsPane active={active} order={menu.map((item) => item.key)} vertical={wide}>
            {active === 'general' ? (
              <SettingsSection
                title="Podstawowe"
                description="Tak sklep przedstawia się klientom i w wiadomościach e-mail."
                {...section('general')}>
                <TextField
                  label="Nazwa sklepu"
                  value={get('general', 'name')}
                  onChangeText={(text) => set('general', 'name', text)}
                  error={fieldError('general', 'name')}
                />
                <TextField
                  label="Krótki opis"
                  hint="Pojawia się pod nazwą sklepu i w wynikach wyszukiwania."
                  value={get('general', 'description')}
                  onChangeText={(text) => set('general', 'description', text)}
                  error={fieldError('general', 'description')}
                  maxLength={500}
                />
                <TextField
                  label="E-mail kontaktowy"
                  hint="Tu przychodzą powiadomienia o zamówieniach i odpowiedzi klientów na e-maile sklepu."
                  value={get('general', 'contact_email')}
                  onChangeText={(text) => set('general', 'contact_email', text)}
                  error={fieldError('general', 'contact_email')}
                  keyboardType="email-address"
                  autoCapitalize="none"
                  autoComplete="email"
                />
              </SettingsSection>
            ) : null}
            {active === 'availability' ? (
              <SettingsSection title="Sklep otwarty" {...section('availability')}>
                <SwitchRow
                  label="Klienci widzą sklep"
                  description={
                    get('availability', 'is_open')
                      ? 'Sklep działa i przyjmuje zamówienia.'
                      : 'Klienci widzą stronę „Wkrótce otwarcie”. Ty widzisz sklep po zalogowaniu do panelu.'
                  }
                  value={get('availability', 'is_open')}
                  onChange={(value) => set('availability', 'is_open', value)}
                />
              </SettingsSection>
            ) : null}
            {active === 'shopping' ? (
              <SettingsSection
                title="Zakupy"
                description="Jak klienci składają zamówienia i co widzą przy produktach."
                {...section('shopping')}>
                <SwitchRow
                  label="Zakupy bez zakładania konta"
                  description="Klient podaje tylko dane do wysyłki."
                  value={get('shopping', 'guest_checkout')}
                  onChange={(value) => set('shopping', 'guest_checkout', value)}
                  error={fieldError('shopping', 'guest_checkout')}
                />
                <SwitchRow
                  label="Zakładanie konta przy zamówieniu"
                  description="Klient może od razu założyć konto i potem śledzić swoje zamówienia."
                  value={get('shopping', 'signup_at_checkout')}
                  onChange={(value) => set('shopping', 'signup_at_checkout', value)}
                />
                <SwitchRow
                  label="Opinie o produktach"
                  description="Klienci mogą oceniać produkty i pisać opinie."
                  value={get('shopping', 'reviews')}
                  onChange={(value) => set('shopping', 'reviews', value)}
                />
                <SwitchRow
                  label="Pilnowanie stanów magazynowych"
                  description="Sklep liczy sztuki i nie sprzeda więcej, niż masz."
                  value={get('shopping', 'manage_stock')}
                  onChange={(value) => set('shopping', 'manage_stock', value)}
                />
                {get('shopping', 'manage_stock') ? (
                  <TextField
                    label="Powiadom mnie, gdy zostanie sztuk"
                    hint="Dostaniesz e-mail, gdy produktu zostanie tyle albo mniej."
                    value={String(get('shopping', 'low_stock_threshold'))}
                    onChangeText={(text) => set('shopping', 'low_stock_threshold', text)}
                    error={fieldError('shopping', 'low_stock_threshold')}
                    keyboardType="number-pad"
                    style={styles.short}
                  />
                ) : null}
              </SettingsSection>
            ) : null}
            {active === 'payments' ? (
              <SettingsSection
                title="Płatności"
                description="Sposoby zapłaty dostępne przy zamówieniu."
                {...section('payments')}>
                <SwitchRow
                  label="Przelew tradycyjny"
                  description="Klient dostaje Twój numer konta i płaci przelewem. Wysyłasz, gdy pieniądze dotrą."
                  value={get('payments', 'bank_transfer_enabled')}
                  onChange={(value) => set('payments', 'bank_transfer_enabled', value)}
                />
                {get('payments', 'bank_transfer_enabled') ? (
                  <View style={styles.nested}>
                    <TextField
                      label="Odbiorca przelewu"
                      placeholder="np. Jan Kowalski albo nazwa firmy"
                      value={get('payments', 'bank_account_name')}
                      onChangeText={(text) => set('payments', 'bank_account_name', text)}
                      error={fieldError('payments', 'bank_account_name')}
                    />
                    <TextField
                      label="Numer konta"
                      placeholder="26 cyfr albo IBAN"
                      value={get('payments', 'bank_account_number')}
                      onChangeText={(text) => set('payments', 'bank_account_number', text)}
                      error={fieldError('payments', 'bank_account_number')}
                      autoCapitalize="characters"
                      autoCorrect={false}
                    />
                    <TextField
                      label="Nazwa banku (opcjonalnie)"
                      value={get('payments', 'bank_name')}
                      onChangeText={(text) => set('payments', 'bank_name', text)}
                      error={fieldError('payments', 'bank_name')}
                    />
                  </View>
                ) : null}
                <SwitchRow
                  label="Płatność przy odbiorze"
                  description="Klient płaci kurierowi albo przy odbiorze osobistym."
                  value={get('payments', 'cash_on_delivery_enabled')}
                  onChange={(value) => set('payments', 'cash_on_delivery_enabled', value)}
                />
                <Note>
                  Płatności internetowe (np. Przelewy24, PayU, karty) wymagają umowy z operatorem płatności. Na razie
                  włączysz je w panelu sklepu.
                </Note>
                <Button
                  title="Przejdź do ustawień ręcznych"
                  icon="chevron"
                  variant="ghost"
                  onPress={() => select('manual')}
                  style={styles.start}
                />
              </SettingsSection>
            ) : null}
            {active === 'shipping' ? (
              <SettingsSection
                title="Wysyłka"
                description={`Sposoby dostawy dla klientów z kraju sklepu. Ceny w ${currency}.`}
                {...section('shipping')}>
                <SwitchRow
                  label="Kurier"
                  value={get('shipping', 'courier_enabled')}
                  onChange={(value) => set('shipping', 'courier_enabled', value)}
                />
                {get('shipping', 'courier_enabled') ? (
                  <TextField
                    label={`Cena wysyłki (${currency})`}
                    value={get('shipping', 'courier_cost')}
                    onChangeText={(text) => set('shipping', 'courier_cost', text)}
                    error={fieldError('shipping', 'courier_cost')}
                    keyboardType="decimal-pad"
                    style={styles.short}
                  />
                ) : null}
                <SwitchRow
                  label="Darmowa dostawa"
                  description="Od wybranej kwoty zamówienia klient nie płaci za wysyłkę."
                  value={get('shipping', 'free_shipping_enabled')}
                  onChange={(value) => set('shipping', 'free_shipping_enabled', value)}
                />
                {get('shipping', 'free_shipping_enabled') ? (
                  <TextField
                    label={`Od kwoty (${currency})`}
                    hint="Wpisz 0, żeby dostawa była zawsze darmowa."
                    value={get('shipping', 'free_shipping_min_amount')}
                    onChangeText={(text) => set('shipping', 'free_shipping_min_amount', text)}
                    error={fieldError('shipping', 'free_shipping_min_amount')}
                    keyboardType="decimal-pad"
                    style={styles.short}
                  />
                ) : null}
                <SwitchRow
                  label="Odbiór osobisty"
                  description="Klient odbiera zamówienie u Ciebie, bez opłaty za wysyłkę."
                  value={get('shipping', 'local_pickup_enabled')}
                  onChange={(value) => set('shipping', 'local_pickup_enabled', value)}
                />
              </SettingsSection>
            ) : null}
            {active === 'taxes' ? (
              <SettingsSection title="Podatki" description="Naliczanie VAT od zamówień." {...section('taxes')}>
                <SwitchRow
                  label="Naliczaj VAT"
                  description="Wyłącz, jeśli korzystasz ze zwolnienia z VAT."
                  value={get('taxes', 'enabled')}
                  onChange={(value) => set('taxes', 'enabled', value)}
                />
                {get('taxes', 'enabled') ? (
                  <View style={styles.nested}>
                    <SwitchRow
                      label="Ceny produktów zawierają VAT"
                      description={
                        get('taxes', 'prices_include_tax')
                          ? 'Wpisujesz ceny brutto, sklep wylicza z nich podatek.'
                          : 'Wpisujesz ceny netto, sklep dolicza podatek przy zamówieniu.'
                      }
                      value={get('taxes', 'prices_include_tax')}
                      onChange={(value) => set('taxes', 'prices_include_tax', value)}
                    />
                    <ChipSelect
                      label="Stawka VAT"
                      options={rateChoices}
                      value={rate}
                      onChange={(value) => set('taxes', 'standard_rate', value)}
                      error={fieldError('taxes', 'standard_rate')}
                    />
                    <Note>
                      Stawka dotyczy wszystkich produktów i wysyłki. Inne stawki dla wybranych produktów ustawisz w
                      panelu sklepu.
                    </Note>
                  </View>
                ) : null}
              </SettingsSection>
            ) : null}
            {active === 'region' ? (
              <SettingsSection
                title="Region"
                description="Język sklepu, waluta cen i kraj, z którego sprzedajesz."
                {...section('region')}>
                <ChipSelect
                  label="Język sklepu"
                  options={options.languages}
                  value={get('region', 'language')}
                  onChange={(value) => set('region', 'language', value)}
                  error={fieldError('region', 'language')}
                />
                <ChipSelect
                  label="Waluta"
                  options={options.currencies}
                  value={currency}
                  onChange={(value) => set('region', 'currency', value)}
                  error={fieldError('region', 'currency')}
                />
                {currency !== values.region.currency ? (
                  <Note warning>Ceny produktów się nie przeliczą. Zmieni się tylko waluta, w której są pokazane.</Note>
                ) : null}
                <ChipSelect
                  label="Kraj"
                  options={options.countries}
                  value={country}
                  onChange={(value) => set('region', 'country', value)}
                  error={fieldError('region', 'country')}
                />
                {country !== values.region.country ? (
                  <Note>
                    Razem z krajem zmienimy strefę czasową, strefę wysyłki i stawkę VAT na typowe dla tego kraju.
                  </Note>
                ) : null}
                <ChipSelect
                  label="Strefa czasowa"
                  options={options.timezones}
                  value={get('region', 'timezone')}
                  onChange={(value) => set('region', 'timezone', value)}
                  error={fieldError('region', 'timezone')}
                />
              </SettingsSection>
            ) : null}
            {active === 'appearance' ? (
              <SettingsSection
                title="Wygląd"
                description="Motyw decyduje o układzie i kolorach sklepu. Produkty i zamówienia zostają bez zmian."
                {...section('appearance')}>
                <ChipSelect
                  label="Motyw"
                  options={options.themes}
                  value={get('appearance', 'theme')}
                  onChange={(value) => set('appearance', 'theme', value)}
                  error={fieldError('appearance', 'theme')}
                />
              </SettingsSection>
            ) : null}
            {active === 'manual' ? (
              <SettingsSection
                title="Ustawienia ręczne"
                description={`Wszystko, czego nie ma w aplikacji, ustawisz w ${panelLocative(settings.panel_name)} swojego sklepu.`}>
                <ShopLoginSteps shopId={Number(id)} />
              </SettingsSection>
            ) : null}
            {active === 'security' ? (
              <SettingsSection title="Bezpieczeństwo">
                <View style={styles.action}>
                  <View style={styles.actionText}>
                    <ThemedText type="smallBold">Nowe hasło administratora</ThemedText>
                    <ThemedText type="small" themeColor="textSecondary">
                      Przyda się, jeśli ktoś mógł poznać obecne hasło. Nowe przyjdzie e-mailem, a wszyscy zalogowani do
                      panelu zostaną wylogowani.
                    </ThemedText>
                  </View>
                  <Button
                    title="Zmień hasło"
                    icon="shield"
                    variant="secondary"
                    disabled={busy || saving === 'security'}
                    onPress={() =>
                      runOperation(
                        'reset-admin-password',
                        'Zmienić hasło administratora?',
                        'Stare hasło przestanie działać, a nowe wyślemy na Twój adres e-mail.',
                        'Zmień hasło',
                      )
                    }
                  />
                </View>
                <View style={styles.action}>
                  <View style={styles.actionText}>
                    <ThemedText type="smallBold">Usuń przykładowe produkty</ThemedText>
                    <ThemedText type="small" themeColor="textSecondary">
                      Produkty dodane przy zakładaniu sklepu. Twoich własnych produktów nie ruszamy.
                    </ThemedText>
                  </View>
                  <Button
                    title="Usuń"
                    variant="danger"
                    disabled={busy || saving === 'security'}
                    onPress={() =>
                      runOperation(
                        'remove-sample-products',
                        'Usunąć przykładowe produkty?',
                        'Produkty „Przykładowy produkt” znikną ze sklepu. Tego nie da się cofnąć.',
                        'Usuń',
                      )
                    }
                  />
                </View>
              </SettingsSection>
            ) : null}
            {active === 'history' ? <History operations={history} /> : null}
          </SettingsPane>
        </View>
      </View>
    </Page>
  );
}

function StatusBar({ settings, onRefresh }: { settings: ShopSettings; onRefresh: () => void }) {
  const theme = useTheme();
  const operation = settings.operation;
  if (settings.busy) {
    const reading = operation?.kind === 'sync_settings';
    return (
      <View style={[styles.status, { backgroundColor: theme.primaryMuted, borderColor: theme.primary }]}>
        <ActivityIndicator color={theme.primary} />
        <ThemedText type="smallBold" themeColor="primary" style={styles.flex}>
          {reading ? 'Sprawdzamy aktualne ustawienia w sklepie…' : 'Wprowadzamy zmiany w sklepie…'}
        </ThemedText>
      </View>
    );
  }
  return (
    <View style={[styles.status, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <Icon name="check" size={18} color="textSecondary" />
      <ThemedText type="small" themeColor="textSecondary" style={styles.flex}>
        {settings.synced_at
          ? `Odczytane ze sklepu ${formatTime(settings.synced_at)}.`
          : 'Ustawienia z formularza zakładania sklepu.'}
      </ThemedText>
      <Button title="Odśwież" icon="refresh" variant="ghost" onPress={onRefresh} />
    </View>
  );
}

function History({ operations }: { operations: ShopOperation[] | undefined }) {
  const theme = useTheme();
  const shown = (operations ?? []).filter((operation) => operation.kind !== 'sync_settings').slice(0, HISTORY_LENGTH);
  return (
    <SettingsSection title="Ostatnie zmiany" description="Zmiany zrobione z aplikacji, od najnowszej.">
      {!shown.length ? (
        <ThemedText type="small" themeColor="textSecondary">
          {operations ? 'Nie ma jeszcze zmian zrobionych z aplikacji.' : 'Wczytujemy historię…'}
        </ThemedText>
      ) : null}
      {shown.map((operation, index) => (
        <View
          key={operation.id}
          style={[styles.historyRow, index > 0 && styles.historyDivider, { borderTopColor: theme.border }]}>
          <View style={styles.flex}>
            <ThemedText type="smallBold">
              {operation.kind === 'update_settings' ? operation.changed_fields.join(', ') : operation.kind_display}
            </ThemedText>
            <ThemedText type="small" themeColor="textSecondary">
              {formatTime(operation.created_at)}
            </ThemedText>
            {operation.status === 'failed' && operation.error ? (
              <ThemedText type="small" themeColor="danger">
                {operation.error}
              </ThemedText>
            ) : null}
          </View>
          <ThemedText type="small" themeColor={operation.status === 'failed' ? 'danger' : 'textSecondary'}>
            {operation.status_display}
          </ThemedText>
        </View>
      ))}
    </SettingsSection>
  );
}

function Note({ children, warning }: { children: string; warning?: boolean }) {
  const theme = useTheme();
  return (
    <View style={[styles.note, { backgroundColor: warning ? theme.accentMuted : theme.surfaceMuted }]}>
      <ThemedText type="small" themeColor={warning ? 'text' : 'textSecondary'}>
        {children}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  loader: {
    marginVertical: Spacing.six,
  },
  header: {
    gap: Spacing.two,
  },
  status: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: Spacing.two,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: Radius.medium,
    borderWidth: 1,
  },
  nested: {
    gap: Spacing.three,
    paddingLeft: Spacing.three,
  },
  short: {
    maxWidth: 200,
  },
  note: {
    padding: Spacing.three,
    borderRadius: Radius.medium,
  },
  action: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: Spacing.three,
  },
  actionText: {
    flexBasis: 260,
    flexGrow: 1,
    gap: Spacing.half,
  },
  start: {
    alignSelf: 'flex-start',
  },
  layout: {
    gap: Spacing.four,
  },
  layoutWide: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  menu: {
    width: 240,
  },
  content: {
    gap: Spacing.three,
  },
  historyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
  },
  historyDivider: {
    paddingTop: Spacing.three,
    borderTopWidth: 1,
  },
});
