import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { router, useLocalSearchParams } from 'expo-router';

import ShopTeamScreen from '@/app/shops/[id]/team';
import { NotificationsProvider } from '@/context/notifications';
import { ApiError } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import type { Team } from '@/lib/types';
import { mockApi, type Routes } from '@/testing/api';
import { shopDetail } from '@/testing/fixtures';

jest.mock('expo-router', () => require('@/testing/router'));
jest.mock('@/lib/api', () => ({ ...jest.requireActual('@/lib/api'), api: jest.fn() }));
jest.mock('@/lib/confirm', () => ({ confirm: jest.fn(async () => true) }));

const TEAM = 'GET /shops/7/team/';

function team(overrides: Partial<Team> = {}): Team {
  return {
    owner: { id: 1, name: 'Anna Kowalska', email: 'anna@example.com' },
    members: [{ id: 2, name: 'Ola Nowak', email: 'ola@example.com', joined_at: '2026-11-18T10:00:00Z' }],
    invitations: [
      { id: 5, email: 'jan@example.com', created_at: '2026-11-19T10:00:00Z', expires_at: '2026-11-26T10:00:00Z', expired: false },
      { id: 6, email: 'ewa@example.com', created_at: '2026-11-01T10:00:00Z', expires_at: '2026-11-08T10:00:00Z', expired: true },
    ],
    limit: 5,
    used: 2,
    ...overrides,
  };
}

async function open(teams: Team | Team[], routes: Routes = {}) {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: '7' });
  const api = mockApi({ 'GET /shops/7/': shopDetail(), [TEAM]: Array.isArray(teams) ? teams : [teams], ...routes });
  await render(<ShopTeamScreen />, { wrapper: NotificationsProvider });
  return { api };
}

beforeEach(() => jest.clearAllMocks());

test('shows the owner, the staff and the invitations with the places taken', async () => {
  await open(team());

  expect(await screen.findByText('Zajęte 2 z 5 miejsc w zespole, licząc wysłane zaproszenia.')).toBeTruthy();
  expect(screen.getByText('Anna Kowalska')).toBeTruthy();
  expect(screen.getByText('Właściciel')).toBeTruthy();
  expect(screen.getByText('Ola Nowak')).toBeTruthy();
  expect(screen.getByText('Ważne do 26 listopada 2026')).toBeTruthy();
  expect(screen.getByText('Wygasło')).toBeTruthy();
  expect(screen.getByText(/^1 czeka na odpowiedź\./)).toBeTruthy();
});

test('invites by e-mail and clears the field', async () => {
  const { api } = await open([team(), team({ used: 3 })], {
    'POST /shops/7/team/invitations/': { id: 9, email: 'nowa@example.com', created_at: '', expires_at: '', expired: false },
  });

  await fireEvent.changeText(await screen.findByLabelText('E-mail'), ' nowa@example.com ');
  await fireEvent.press(screen.getByRole('button', { name: 'Wyślij zaproszenie' }));

  expect(api.sent('POST /shops/7/team/invitations/')).toEqual([{ email: 'nowa@example.com' }]);
  expect(await screen.findByText('Zaproszenie wysłane na nowa@example.com.')).toBeTruthy();
  expect(screen.getByLabelText('E-mail')).toHaveProp('value', '');
  expect(await screen.findByText(/Zajęte 3 z 5/)).toBeTruthy();
});

test('a wrong address is explained under the field', async () => {
  await open(team(), {
    'POST /shops/7/team/invitations/': new ApiError(400, { email: ['Ta osoba jest już w zespole sklepu.'] }),
  });

  await fireEvent.changeText(await screen.findByLabelText('E-mail'), 'ola@example.com');
  await fireEvent.press(screen.getByRole('button', { name: 'Wyślij zaproszenie' }));

  expect(await screen.findByText('Ta osoba jest już w zespole sklepu.')).toBeTruthy();
  expect(screen.getByLabelText('E-mail')).toHaveProp('value', 'ola@example.com');
});

test('a full team points to changing the plan', async () => {
  await open(team({ used: 5 }));

  expect(await screen.findByText(/Twój plan pozwala na 5 osób z obsługi w tym sklepie\./)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Wyślij zaproszenie' })).toBeDisabled();
  await fireEvent.press(screen.getByRole('button', { name: 'Zmień plan' }));
  expect(router.push).toHaveBeenCalledWith('/billing/change');
});

test('an invitation can be sent again or revoked', async () => {
  const { api } = await open(team(), {
    'POST /shops/7/team/invitations/': { id: 6, email: 'ewa@example.com', created_at: '', expires_at: '', expired: false },
    'DELETE /shops/7/team/invitations/5/': null,
  });

  await fireEvent.press(await screen.findByRole('button', { name: 'Zaproś ponownie' }));
  expect(api.sent('POST /shops/7/team/invitations/')).toEqual([{ email: 'ewa@example.com' }]);
  expect(await screen.findByText('Zaproszenie wysłane na ewa@example.com.')).toBeTruthy();

  await fireEvent.press(screen.getByRole('button', { name: 'Cofnij zaproszenie dla jan@example.com' }));
  expect(confirm).toHaveBeenCalledWith('Cofnąć zaproszenie?', expect.stringContaining('jan@example.com'), 'Cofnij zaproszenie');
  await waitFor(() => expect(api.sent('DELETE /shops/7/team/invitations/5/')).toHaveLength(1));
  expect(await screen.findByText('Zaproszenie dla jan@example.com cofnięte.')).toBeTruthy();
});

test('removing someone asks first', async () => {
  const { api } = await open(team(), { 'DELETE /shops/7/team/members/2/': null });

  await fireEvent.press(await screen.findByRole('button', { name: 'Usuń Ola Nowak z zespołu' }));

  expect(confirm).toHaveBeenCalledWith('Usunąć z zespołu?', expect.stringContaining('Ola Nowak'), 'Usuń z zespołu');
  await waitFor(() => expect(api.sent('DELETE /shops/7/team/members/2/')).toHaveLength(1));
  expect(await screen.findByText('Ola Nowak nie jest już w zespole.')).toBeTruthy();
});
