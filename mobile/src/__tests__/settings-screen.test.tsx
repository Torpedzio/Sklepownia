import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { Linking } from 'react-native';

import ShopSettingsScreen from '@/app/shops/[id]/settings';
import { NotificationsProvider } from '@/context/notifications';
import { ApiError } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import type { ShopOperation } from '@/lib/types';
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

  expect(await screen.findByText(/Na razie\s+włączysz je w panelu sklepu\./)).toBeTruthy();
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
