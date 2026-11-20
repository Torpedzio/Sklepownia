import { fireEvent, render, screen } from '@testing-library/react-native';
import { useLocalSearchParams } from 'expo-router';

import ShopHistoryScreen from '@/app/shops/[id]/history';
import { useAuth } from '@/context/auth';
import { NotificationsProvider } from '@/context/notifications';
import type { ShopEvent } from '@/lib/types';
import { mockApi } from '@/testing/api';
import { shopDetail } from '@/testing/fixtures';

jest.mock('expo-router', () => require('@/testing/router'));
jest.mock('@/lib/api', () => ({ ...jest.requireActual('@/lib/api'), api: jest.fn() }));
jest.mock('@/context/auth', () => ({ useAuth: jest.fn() }));

const anna = { id: 1, name: 'Anna Kowalska', email: 'anna@example.com' };
const ola = { id: 2, name: 'Ola Nowak', email: 'ola@example.com' };

function event(id: number, fields: Partial<ShopEvent>): ShopEvent {
  return {
    id,
    kind: 'operation',
    title: 'Zmiana ustawień',
    detail: '',
    actor: anna,
    actor_role: 'owner',
    status: null,
    error: '',
    created_at: new Date().toISOString(),
    ...fields,
  };
}

async function open(routes: Record<string, unknown>) {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: '7' });
  (useAuth as jest.Mock).mockReturnValue({ user: { id: 1 } });
  const api = mockApi({ 'GET /shops/7/': shopDetail(), ...routes });
  await render(<ShopHistoryScreen />, { wrapper: NotificationsProvider });
  return { api };
}

beforeEach(() => jest.clearAllMocks());

test('says who did what, grouped by day', async () => {
  await open({
    'GET /shops/7/history/': {
      events: [
        event(4, { title: 'Zmiana ustawień', detail: 'Waluta, Język', status: 'succeeded' }),
        event(3, { title: 'Dołączenie do zespołu', actor: ola, actor_role: 'staff', kind: 'member_joined' }),
        event(2, { title: 'Zawieszenie sklepu', actor: null, actor_role: 'system', created_at: '2026-11-01T10:00:00Z' }),
        event(1, { title: 'Odejście z zespołu', actor: null, actor_role: 'deleted', created_at: '2026-11-01T09:00:00Z' }),
      ],
      has_more: false,
    },
  });

  expect(await screen.findByText('Dziś')).toBeTruthy();
  expect(screen.getByText('Waluta, Język')).toBeTruthy();
  expect(screen.getByText('Ty')).toBeTruthy();
  expect(screen.getByText('Ola Nowak (obsługa)')).toBeTruthy();
  expect(screen.getByText('1 listopada 2026')).toBeTruthy();
  expect(screen.getByText('Sklepownia, automatycznie')).toBeTruthy();
  expect(screen.getByText('Usunięte konto')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Pokaż starsze' })).toBeNull();
});

test('a failed change says why', async () => {
  await open({
    'GET /shops/7/history/': {
      events: [event(1, { title: 'Kopia zapasowa', status: 'failed', error: 'Sklep nie odpowiedział.' })],
      has_more: false,
    },
  });

  expect(await screen.findByText('Nie udało się')).toBeTruthy();
  expect(screen.getByText('Sklep nie odpowiedział.')).toBeTruthy();
});

test('older entries load on request', async () => {
  const { api } = await open({
    'GET /shops/7/history/': { events: [event(9, { title: 'Nowsze' })], has_more: true },
    'GET /shops/7/history/?before=9': { events: [event(8, { title: 'Starsze' })], has_more: false },
  });

  await fireEvent.press(await screen.findByRole('button', { name: 'Pokaż starsze' }));

  expect(await screen.findByText('Starsze')).toBeTruthy();
  expect(screen.getByText('Nowsze')).toBeTruthy();
  expect(api.calls.map((call) => call.key)).toContain('GET /shops/7/history/?before=9');
  expect(screen.queryByRole('button', { name: 'Pokaż starsze' })).toBeNull();
});
