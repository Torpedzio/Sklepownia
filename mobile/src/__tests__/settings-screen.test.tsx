import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { Linking } from 'react-native';

import ShopSettingsScreen from '@/app/shops/[id]/settings';
import { NotificationsProvider } from '@/context/notifications';
import { ApiError } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import type { ShopBackup, ShopBackups, ShopOperation, ShopSettings } from '@/lib/types';
import { mockApi, type Routes } from '@/testing/api';
import { shopSettings } from '@/testing/fixtures';

jest.mock('expo-router', () => require('@/testing/router'));
jest.mock('@/lib/api', () => ({ ...jest.requireActual('@/lib/api'), api: jest.fn() }));
jest.mock('@/lib/confirm', () => ({ confirm: jest.fn(async () => true) }));

const SETTINGS = 'GET /shops/7/settings/';
const SAVE = 'PATCH /shops/7/settings/';
// Read just now, so opening the screen doesn't ask the shop again.
const fresh = { synced_at: new Date().toISOString() };

function operation(overrides: Partial<ShopOperation> = {}): ShopOperation {
  return {
    id: 5,
    kind: 'update_settings',
    kind_display: 'Zmiana ustawień',
    status: 'queued',
    status_display: 'W kolejce',
    changes: {},
    changed_fields: [],
    result: {},
    backup_created_at: null,
    error: '',
    created_at: new Date().toISOString(),
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}

async function open(section: string | undefined, routes: Routes) {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: '7', section });
  const api = mockApi({ 'GET /shops/7/operations/': [[]], ...routes });
  await render(<ShopSettingsScreen />, { wrapper: NotificationsProvider });
  return { api };
}

beforeEach(() => jest.clearAllMocks());

test('opens on the basic settings with the values from the shop', async () => {
  await open(undefined, { [SETTINGS]: shopSettings({}, fresh) });

  expect(await screen.findByDisplayValue('Palarnia')).toBeTruthy();
  expect(screen.getByDisplayValue('kontakt@example.com')).toBeTruthy();
  expect(screen.getByText(/Odczytane ze sklepu dziś/)).toBeTruthy();
});

test('asks the shop for its current settings when the last read is old', async () => {
  const { api } = await open(undefined, {
    [SETTINGS]: shopSettings({}, { synced_at: '2026-01-01T10:00:00Z' }),
    'POST /shops/7/settings/refresh/': shopSettings(),
  });

  await waitFor(() => expect(api.sent('POST /shops/7/settings/refresh/')).toHaveLength(1));
});

test('a change that ended while the screen was closed is not announced on coming back', async () => {
  await open(undefined, {
    [SETTINGS]: shopSettings({}, { ...fresh, busy: true, operation: operation({ status: 'running' }) }),
  });
  expect(await screen.findByText('Wprowadzamy zmiany w sklepie…')).toBeTruthy();
  await screen.unmount();

  // Back later: the cached copy shows until the shop's settings arrive.
  let answer!: (settings: ShopSettings) => void;
  const { api } = await open(undefined, {
    [SETTINGS]: () => new Promise<ShopSettings>((resolve) => (answer = resolve)),
  });
  expect(screen.getByText('Wprowadzamy zmiany w sklepie…')).toBeTruthy();
  const done = operation({ status: 'succeeded', changed_fields: ['Nazwa sklepu'] });
  await act(async () => answer(shopSettings({}, { ...fresh, operation: done })));

  expect(await screen.findByText(/Odczytane ze sklepu dziś/)).toBeTruthy();
  expect(screen.queryByText('Zapisano w sklepie: nazwa sklepu.')).toBeNull();
  expect(api.sent('POST /shops/7/settings/refresh/')).toHaveLength(0);
});

test('the menu switches sections through the address', async () => {
  await open(undefined, { [SETTINGS]: shopSettings({}, fresh) });

  await fireEvent.press(await screen.findByRole('tab', { name: 'Płatności' }));

  expect(router.setParams).toHaveBeenCalledWith({ section: 'platnosci' });
});

test('saving a section sends only the changes and reports when the shop has them', async () => {
  const saved = shopSettings(
    { general: { name: 'Nowa Palarnia' } },
    { ...fresh, operation: operation({ status: 'succeeded', changed_fields: ['Nazwa sklepu'] }) },
  );
  const { api } = await open(undefined, {
    [SETTINGS]: [shopSettings({}, fresh), saved],
    [SAVE]: shopSettings({}, { ...fresh, busy: true, operation: operation() }),
  });

  await fireEvent.changeText(await screen.findByDisplayValue('Palarnia'), 'Nowa Palarnia');
  await fireEvent.press(screen.getByRole('button', { name: 'Zapisz' }));

  expect(api.sent(SAVE)).toEqual([{ general: { name: 'Nowa Palarnia' } }]);
  expect(await screen.findByText('Zapisano w sklepie: nazwa sklepu.')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Zapisz' })).toBeNull();
});

test('a failed change is reported with its reason', async () => {
  const failed = shopSettings(
    {},
    { ...fresh, operation: operation({ status: 'failed', error: 'Sklep nie odpowiada.' }) },
  );
  await open(undefined, {
    [SETTINGS]: [shopSettings({}, fresh), failed],
    [SAVE]: shopSettings({}, { ...fresh, busy: true, operation: operation() }),
  });

  await fireEvent.changeText(await screen.findByDisplayValue('Palarnia'), 'Inna');
  await fireEvent.press(screen.getByRole('button', { name: 'Zapisz' }));

  expect(await screen.findByText('Sklep nie odpowiada.')).toBeTruthy();
  // The edit stays, so it can be saved again.
  expect(screen.getByDisplayValue('Inna')).toBeTruthy();
});

test('field errors from the API show under the fields', async () => {
  await open(undefined, {
    [SETTINGS]: shopSettings({}, fresh),
    [SAVE]: new ApiError(400, { general: { contact_email: ['Podaj poprawny adres e-mail.'] } }),
  });

  await fireEvent.changeText(await screen.findByDisplayValue('kontakt@example.com'), 'zly-adres');
  await fireEvent.press(screen.getByRole('button', { name: 'Zapisz' }));

  expect(await screen.findByText('Podaj poprawny adres e-mail.')).toBeTruthy();
  expect(screen.getByText('Popraw zaznaczone pola.')).toBeTruthy();
});

test('saving values the shop already has changes nothing', async () => {
  await open(undefined, { [SETTINGS]: shopSettings({}, fresh), [SAVE]: shopSettings({}, fresh) });

  await fireEvent.changeText(await screen.findByDisplayValue('Kawa'), 'Kawa ');
  await fireEvent.press(screen.getByRole('button', { name: 'Zapisz' }));

  expect(await screen.findByText('Sklep ma już te ustawienia.')).toBeTruthy();
});

test('undo brings back the saved value', async () => {
  await open(undefined, { [SETTINGS]: shopSettings({}, fresh) });

  await fireEvent.changeText(await screen.findByDisplayValue('Palarnia'), 'Inna');
  await fireEvent.press(screen.getByRole('button', { name: 'Cofnij' }));

  expect(screen.getByDisplayValue('Palarnia')).toBeTruthy();
});

test('bank transfer asks for the account and the menu marks unsaved edits', async () => {
  const { api } = await open('platnosci', {
    [SETTINGS]: shopSettings({}, fresh),
    [SAVE]: shopSettings({}, { ...fresh, busy: true, operation: operation() }),
  });

  await fireEvent.press(await screen.findByRole('switch', { name: 'Przelew tradycyjny' }));
  await fireEvent.changeText(screen.getByPlaceholderText('26 cyfr albo IBAN'), '61109010140000071219812874');

  expect(screen.getByRole('tab', { name: 'Płatności, niezapisane zmiany' })).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Zapisz' }));
  expect(api.sent(SAVE)).toEqual([
    { payments: { bank_transfer_enabled: true, bank_account_number: '61109010140000071219812874' } },
  ]);
});

test('an online payment operator asks for its account and keys and sends them to the shop', async () => {
  const saved = shopSettings(
    { payments: { przelewy24_enabled: true, przelewy24_merchant_id: '123456', przelewy24_keys_saved: true } },
    {
      ...fresh,
      operation: operation({
        status: 'succeeded',
        changes: { payments: {} },
        changed_fields: ['Płatności Przelewy24', 'ID sprzedawcy Przelewy24', 'Klucz CRC Przelewy24'],
      }),
    },
  );
  const { api } = await open('platnosci', {
    [SETTINGS]: [shopSettings({}, fresh), saved],
    [SAVE]: shopSettings({}, { ...fresh, busy: true, operation: operation() }),
  });

  expect(screen.queryByLabelText('ID sprzedawcy')).toBeNull();
  await fireEvent.press(await screen.findByRole('switch', { name: 'Przelewy24' }));
  await fireEvent.changeText(screen.getByLabelText('ID sprzedawcy'), '123456');
  await fireEvent.changeText(screen.getByLabelText('Klucz CRC'), '0123456789abcdef');
  await fireEvent.changeText(screen.getByLabelText('Klucz API'), 'fedcba9876543210fedcba9876543210');

  expect(screen.getByLabelText('Klucz CRC')).toHaveProp('secureTextEntry', true);
  expect(screen.getByText(/dodaj adres IP serwera sklepu: 203\.0\.113\.7\./)).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Zapisz' }));

  expect(api.sent(SAVE)).toEqual([
    {
      payments: {
        przelewy24_enabled: true,
        przelewy24_merchant_id: '123456',
        przelewy24_crc_key: '0123456789abcdef',
        przelewy24_api_key: 'fedcba9876543210fedcba9876543210',
      },
    },
  ]);
  // Labels that start with a name keep its capital letter.
  const fields = 'płatności Przelewy24, ID sprzedawcy Przelewy24, klucz CRC Przelewy24';
  expect(await screen.findByText(`Zapisano w sklepie: ${fields}.`)).toBeTruthy();
  // The keys are in the shop now; the screen forgets them.
  expect(screen.getByLabelText('Klucz CRC')).toHaveProp('value', '');
  expect(screen.getByLabelText('Klucz CRC')).toHaveProp('placeholder', '••••••••');
});

test('keys already in the shop are not asked for again, unless the mode changes', async () => {
  const { api } = await open('platnosci', {
    [SETTINGS]: shopSettings(
      { payments: { payu_enabled: true, payu_pos_id: '300746', payu_client_id: '300746', payu_keys_saved: true } },
      fresh,
    ),
    [SAVE]: shopSettings({}, { ...fresh, busy: true, operation: operation() }),
  });

  expect(await screen.findByLabelText('Drugi klucz (MD5)')).toHaveProp('placeholder', '••••••••');
  expect(screen.getAllByText('Zapisany w sklepie. Wpisz nowy tylko, jeśli chcesz go zmienić.')).toHaveLength(2);

  await fireEvent.changeText(screen.getByLabelText('Id punktu płatności (pos_id)'), '300747');
  await fireEvent.press(screen.getByRole('button', { name: 'Zapisz' }));
  expect(api.sent(SAVE)).toEqual([{ payments: { payu_pos_id: '300747' } }]);

  await fireEvent.press(screen.getByRole('switch', { name: 'Tryb testowy' }));
  expect(screen.getByLabelText('Drugi klucz (MD5)')).toHaveProp('placeholder', '32 znaki');
  expect(screen.queryByText('Zapisany w sklepie. Wpisz nowy tylko, jeśli chcesz go zmienić.')).toBeNull();
});

test('without operators the app sets up, online payments are left to the shop panel', async () => {
  await open('platnosci', { [SETTINGS]: shopSettings({}, { ...fresh, payment_operators: [] }) });

  expect(await screen.findByText(/w panelu\s+PayPal, a Przelewy24 i PayU nie są jeszcze dostępne\./)).toBeTruthy();
  expect(screen.queryByRole('switch', { name: 'Przelewy24' })).toBeNull();
});

test('without the server address Przelewy24 says to ask for it', async () => {
  await open('platnosci', {
    [SETTINGS]: shopSettings({ payments: { przelewy24_enabled: true } }, { ...fresh, server_ip: null }),
  });

  expect(await screen.findByText(/Napisz do nas, a podamy adres IP/)).toBeTruthy();
});

test('shipping prices typed with a comma are sent as numbers', async () => {
  const { api } = await open('wysylka', {
    [SETTINGS]: shopSettings({ shipping: { courier_enabled: true } }, fresh),
    [SAVE]: shopSettings({}, { ...fresh, busy: true, operation: operation() }),
  });

  await fireEvent.changeText(await screen.findByDisplayValue('15.00'), '12,50');
  await fireEvent.press(screen.getByRole('button', { name: 'Zapisz' }));

  expect(api.sent(SAVE)).toEqual([{ shipping: { courier_cost: '12.50' } }]);
});

test('taxes offer the rates usual in the shop country', async () => {
  await open('podatki', { [SETTINGS]: shopSettings({ taxes: { enabled: true } }, fresh) });

  expect(await screen.findByRole('radio', { name: '23%' })).toBeTruthy();
  expect(screen.getByRole('radio', { name: '8%' })).toBeTruthy();
});

test('region changes are confirmed first and warn about prices', async () => {
  (confirm as jest.Mock).mockResolvedValueOnce(false);
  const { api } = await open('region', { [SETTINGS]: shopSettings({}, fresh) });

  await fireEvent.press(await screen.findByRole('radio', { name: 'Euro (EUR)' }));
  expect(screen.getByText(/Ceny produktów się nie przeliczą/)).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Zapisz' }));

  expect(confirm).toHaveBeenCalled();
  expect(api.sent(SAVE)).toEqual([]);
});

test('a new admin password is reported when ready', async () => {
  const started = operation({ kind: 'reset_admin_password', kind_display: 'Nowe hasło administratora' });
  const done = shopSettings({}, { ...fresh, operation: { ...started, status: 'succeeded' } });
  const { api } = await open('bezpieczenstwo', {
    [SETTINGS]: [shopSettings({}, fresh), done],
    'POST /shops/7/reset-admin-password/': started,
  });

  await fireEvent.press(await screen.findByRole('button', { name: 'Zmień hasło' }));

  expect(api.sent('POST /shops/7/reset-admin-password/')).toHaveLength(1);
  expect(await screen.findByText('Nowe hasło administratora wysłaliśmy na Twój adres e-mail.')).toBeTruthy();
});

test('removing sample products says how many went', async () => {
  const started = operation({ kind: 'remove_sample_products' });
  const done = shopSettings({}, { ...fresh, operation: { ...started, status: 'succeeded', result: { removed: 6 } } });
  await open('bezpieczenstwo', {
    [SETTINGS]: [shopSettings({}, fresh), done],
    'POST /shops/7/remove-sample-products/': started,
  });

  await fireEvent.press(await screen.findByRole('button', { name: 'Usuń' }));

  expect(await screen.findByText('Usunięto przykładowe produkty (6).')).toBeTruthy();
});

test('manual settings never show the password, they send it by e-mail', async () => {
  const openURL = jest.spyOn(Linking, 'openURL').mockResolvedValue();
  const access = { admin_url: 'http://palarnia.localhost/wp-admin/', sent_to: 'anna@example.com' };
  const { api } = await open('reczne', {
    [SETTINGS]: shopSettings({}, fresh),
    'GET /shops/7/admin-access/': access,
    'POST /shops/7/send-admin-access/': [access, new ApiError(429, null)],
  });

  await fireEvent.press(await screen.findByRole('button', { name: 'Otwórz panel sklepu' }));
  expect(openURL).toHaveBeenCalledWith('http://palarnia.localhost/wp-admin/');

  await fireEvent.press(screen.getByRole('button', { name: 'Wyślij dane ponownie' }));
  expect(await screen.findByText('Wysłaliśmy dane logowania na anna@example.com.')).toBeTruthy();
  expect(api.sent('POST /shops/7/send-admin-access/')).toHaveLength(1);

  await fireEvent.press(screen.getByRole('button', { name: 'Wyślij dane ponownie' }));
  expect(await screen.findByText('Dane wysłaliśmy już kilka razy. Spróbuj ponownie za godzinę.')).toBeTruthy();
});

test('history lists the changes made from the app', async () => {
  await open('historia', {
    [SETTINGS]: shopSettings({}, fresh),
    'GET /shops/7/operations/': [
      [
        operation({
          id: 2,
          status: 'failed',
          status_display: 'Błąd',
          changed_fields: ['Waluta'],
          error: 'Nie wyszło.',
        }),
        operation({ id: 1, kind: 'sync_settings', status: 'succeeded' }),
      ],
    ],
  });

  expect(await screen.findByText('Waluta')).toBeTruthy();
  expect(screen.getByText('Nie wyszło.')).toBeTruthy();
});

test('while the shop is busy the screen says so and saving waits', async () => {
  await open(undefined, {
    [SETTINGS]: shopSettings({}, { ...fresh, busy: true, operation: operation({ status: 'running' }) }),
  });

  expect(await screen.findByText('Wprowadzamy zmiany w sklepie…')).toBeTruthy();
  await fireEvent.changeText(screen.getByDisplayValue('Palarnia'), 'Inna');
  expect(screen.getByText(/gdy sklep skończy wprowadzać poprzednie zmiany/)).toBeTruthy();
});

test('a settings page that fails to load says why', async () => {
  await open(undefined, { [SETTINGS]: new ApiError(409, { detail: 'Sklep jeszcze się zakłada.' }) });

  expect(await screen.findByText('Sklep jeszcze się zakłada.')).toBeTruthy();
});

test('the menu has only the sections the shop platform lets the app change', async () => {
  const presta = shopSettings({}, {
    ...fresh,
    sections: ['general', 'availability', 'payments', 'appearance'],
    panel_name: 'panel PrestaShop',
  });
  await open('wysylka', { [SETTINGS]: presta, 'GET /shops/7/admin-access/': { admin_url: 'x', sent_to: 'a@b.pl' } });

  expect(await screen.findByRole('tab', { name: 'Płatności' })).toBeTruthy();
  expect(screen.queryByRole('tab', { name: 'Wysyłka' })).toBeNull();
  expect(screen.queryByRole('tab', { name: 'Region' })).toBeNull();
  // An address pointing at a missing section opens the first one.
  expect(screen.getByDisplayValue('Palarnia')).toBeTruthy();
});

// --- terms and privacy policy ---

const PREVIEW = 'POST /shops/7/documents/preview/';

test('the terms are published after a warning that they replace the shop’s own', async () => {
  const saved = shopSettings(
    { documents: { managed: true, terms_url: 'http://palarnia.localhost:8080/regulamin/' } },
    {
      ...fresh,
      operation: operation({
        status: 'succeeded',
        changes: { documents: { managed: true, return_days: 30 } },
        changed_fields: ['Regulamin i polityka prywatności z aplikacji', 'Dni na odstąpienie od umowy'],
      }),
    },
  );
  const { api } = await open('regulamin', {
    [SETTINGS]: [shopSettings({}, fresh), saved],
    [SAVE]: shopSettings({}, { ...fresh, busy: true, operation: operation() }),
  });

  // Seller details come from the billing profile.
  expect(await screen.findByDisplayValue('Palarnia Jan Kowalski')).toBeTruthy();
  await fireEvent.press(screen.getByRole('switch', { name: 'Regulamin i polityka prywatności z aplikacji' }));
  expect(screen.getByText(/Obecny regulamin i politykę prywatności sklepu zastąpimy nowymi/)).toBeTruthy();
  await fireEvent.changeText(screen.getByDisplayValue('14'), '30');
  await fireEvent.press(screen.getByRole('button', { name: 'Zapisz' }));

  expect(api.sent(SAVE)).toEqual([{ documents: { managed: true, return_days: 30 } }]);
  expect(await screen.findByText('Regulamin i polityka prywatności są już w sklepie.')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Regulamin w sklepie' })).toBeTruthy();
});

test('the preview shows the documents as they would be with the edits', async () => {
  const { api } = await open('regulamin', {
    [SETTINGS]: shopSettings({}, fresh),
    [PREVIEW]: {
      documents: [
        {
          key: 'terms',
          title: 'Regulamin sklepu',
          blocks: [
            { type: 'heading', level: 2, text: '§ 1. Postanowienia ogólne' },
            { type: 'paragraph', text: 'Sklep prowadzi Palarnia Kawy Sp. z o.o.' },
            { type: 'list', ordered: true, items: [{ text: 'Przelew', items: [{ text: 'na konto' }] }] },
          ],
        },
        {
          key: 'privacy',
          title: 'Polityka prywatności',
          blocks: [{ type: 'heading', level: 2, text: '1. Administrator danych' }],
        },
      ],
    },
  });

  await fireEvent.changeText(await screen.findByDisplayValue('Palarnia Jan Kowalski'), 'Palarnia Kawy Sp. z o.o.');
  await fireEvent.press(screen.getByRole('button', { name: 'Podgląd dokumentów' }));

  expect(api.sent(PREVIEW)).toEqual([{ documents: { seller_name: 'Palarnia Kawy Sp. z o.o.' } }]);
  expect(await screen.findByText('§ 1. Postanowienia ogólne')).toBeTruthy();
  expect(screen.getByText('Sklep prowadzi Palarnia Kawy Sp. z o.o.')).toBeTruthy();
  expect(screen.getByText('na konto')).toBeTruthy();
  await fireEvent.press(screen.getByRole('radio', { name: 'Polityka prywatności' }));
  expect(screen.getByText('1. Administrator danych')).toBeTruthy();
  expect(screen.queryByText('§ 1. Postanowienia ogólne')).toBeNull();
});

test('a preview of documents missing the seller’s details points at the fields', async () => {
  await open('regulamin', {
    [SETTINGS]: shopSettings({}, fresh),
    [PREVIEW]: new ApiError(400, { documents: { city: ['Potrzebne do regulaminu.'] } }),
  });

  await fireEvent.press(await screen.findByRole('button', { name: 'Podgląd dokumentów' }));

  expect(await screen.findByText('Potrzebne do regulaminu.')).toBeTruthy();
  expect(screen.getByText('Uzupełnij zaznaczone pola, żeby zobaczyć podgląd.')).toBeTruthy();
});

test('the published documents open in the shop', async () => {
  const openURL = jest.spyOn(Linking, 'openURL').mockResolvedValue();
  await open('regulamin', {
    [SETTINGS]: shopSettings(
      {
        documents: {
          managed: true,
          terms_url: 'http://palarnia.localhost:8080/regulamin/',
          privacy_url: 'http://palarnia.localhost:8080/polityka-prywatnosci/',
        },
      },
      fresh,
    ),
  });

  await fireEvent.press(await screen.findByRole('button', { name: 'Polityka prywatności w sklepie' }));

  expect(openURL).toHaveBeenCalledWith('http://palarnia.localhost:8080/polityka-prywatnosci/');
  expect(screen.queryByText(/zastąpimy nowymi/)).toBeNull();
});

test('the templates are only for shops selling from Poland', async () => {
  await open('regulamin', { [SETTINGS]: shopSettings({ region: { country: 'DE' } }, fresh) });

  expect(await screen.findByText(/Wzory są na razie dla sklepów sprzedających z Polski/)).toBeTruthy();
  expect(
    screen.getByRole('switch', { name: 'Regulamin i polityka prywatności z aplikacji' }).props.accessibilityState,
  ).toMatchObject({ disabled: true });
});

const BACKUPS = 'GET /shops/7/backups/';
// Local times, so the screen shows the same in any time zone.
const monday = new Date(2026, 10, 16, 3, 0).toISOString();
const nightly: ShopBackup = { id: 11, kind: 'nightly', kind_display: 'Kopia nocna', created_at: monday, size: 215_000_000 };

function shopBackups(overrides: Partial<ShopBackups> = {}): ShopBackups {
  return {
    enabled: true,
    backups: [],
    manual_left: 3,
    manual_per_day: 3,
    keep_daily: 7,
    keep_weekly: 4,
    nightly_at: new Date(2026, 10, 20, 3, 0).toISOString(),
    ...overrides,
  };
}

test('backups are listed, and one is made now without asking', async () => {
  const started = operation({ id: 8, kind: 'create_backup' });
  const done = shopSettings({}, { ...fresh, operation: { ...started, status: 'succeeded' } });
  const { api } = await open('kopie', {
    [SETTINGS]: [shopSettings({}, fresh), done],
    [BACKUPS]: shopBackups({ backups: [nightly] }),
    'POST /shops/7/backups/': started,
  });

  expect(await screen.findByText('16 listopada, 03:00')).toBeTruthy();
  expect(screen.getByText('Kopia nocna, 215 MB')).toBeTruthy();
  expect(screen.getByText(/Zostaje najnowsza kopia z każdego z ostatnich 7 dni i 4 tygodni/)).toBeTruthy();
  expect(screen.getByText(/Dziś możesz zrobić jeszcze 3/)).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Zrób kopię' }));

  expect(confirm).not.toHaveBeenCalled();
  expect(api.sent('POST /shops/7/backups/')).toHaveLength(1);
  expect(await screen.findByText('Kopia zapasowa jest gotowa.')).toBeTruthy();
  // The list is read again, with the new backup.
  await waitFor(() => expect(api.calls.filter((call) => call.key === BACKUPS).length).toBeGreaterThan(1));
});

test('restoring a backup asks first, and then says which one is back', async () => {
  const started = operation({ id: 9, kind: 'restore_backup', backup_created_at: monday });
  const done = shopSettings({}, { ...fresh, operation: { ...started, status: 'succeeded' } });
  const { api } = await open('kopie', {
    [SETTINGS]: [shopSettings({}, fresh), done],
    [BACKUPS]: shopBackups({ backups: [nightly] }),
    'POST /shops/7/backups/11/restore/': started,
  });

  await fireEvent.press(await screen.findByRole('button', { name: 'Przywróć kopię z 16 listopada, 03:00' }));

  expect(confirm).toHaveBeenCalledWith(
    'Przywrócić kopię z 16 listopada, 03:00?',
    expect.stringContaining('zamówienia i zmiany zrobione później znikną ze sklepu'),
    'Przywróć',
  );
  expect(api.sent('POST /shops/7/backups/11/restore/')).toHaveLength(1);
  expect(
    await screen.findByText('Przywróciliśmy kopię z 16 listopada, 03:00. Stan sprzed przywrócenia jest na liście kopii.'),
  ).toBeTruthy();
});

test('nothing is restored without saying yes', async () => {
  (confirm as jest.Mock).mockResolvedValueOnce(false);
  const { api } = await open('kopie', {
    [SETTINGS]: shopSettings({}, fresh),
    [BACKUPS]: shopBackups({ backups: [nightly] }),
  });

  await fireEvent.press(await screen.findByRole('button', { name: 'Przywróć kopię z 16 listopada, 03:00' }));

  expect(api.calls.map((call) => call.key)).not.toContain('POST /shops/7/backups/11/restore/');
});

test('a new shop learns when its first backup comes, and the backups of the day run out', async () => {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  tomorrow.setHours(3, 0, 0, 0);
  await open('kopie', {
    [SETTINGS]: shopSettings({}, fresh),
    [BACKUPS]: shopBackups({ manual_left: 0, nightly_at: tomorrow.toISOString() }),
  });

  expect(await screen.findByText('Kopii jeszcze nie ma. Pierwsza powstanie jutro o 03:00.')).toBeTruthy();
  expect(screen.getByText(/Na dziś to już wszystkie kopie/)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Zrób kopię' }).props.accessibilityState).toMatchObject({ disabled: true });
});

test('while a backup is restored the screen says the shop is closed for a while', async () => {
  await open('kopie', {
    [SETTINGS]: shopSettings({}, { ...fresh, busy: true, operation: operation({ kind: 'restore_backup', status: 'running' }) }),
    [BACKUPS]: shopBackups({ backups: [nightly] }),
  });

  expect(await screen.findByText('Przywracamy sklep z kopii. Przez kilka minut będzie nieczynny…')).toBeTruthy();
  expect(
    screen.getByRole('button', { name: 'Przywróć kopię z 16 listopada, 03:00' }).props.accessibilityState,
  ).toMatchObject({ disabled: true });
});

test('backups switched off on the platform are not offered', async () => {
  await open('kopie', { [SETTINGS]: shopSettings({}, fresh), [BACKUPS]: shopBackups({ enabled: false }) });

  expect(await screen.findByText(/Kopie zapasowe są chwilowo wyłączone/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Zrób kopię' })).toBeNull();
});

