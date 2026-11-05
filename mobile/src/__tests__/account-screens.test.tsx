import { act, fireEvent, render, screen } from '@testing-library/react-native';

import AccountScreen from '@/app/(tabs)/account';
import ShopsScreen from '@/app/(tabs)/shops';
import ContactScreen from '@/app/contact';
import SignInScreen from '@/app/sign-in';
import SignUpScreen from '@/app/sign-up';
import VerifyEmailScreen from '@/app/verify-email';
import { useAuth } from '@/context/auth';
import { NotificationsProvider } from '@/context/notifications';
import { ApiError } from '@/lib/api';
import type { Shop, User } from '@/lib/types';
import { mockApi } from '@/testing/api';
import { router } from '@/testing/router';

jest.mock('expo-router', () => require('@/testing/router'));
jest.mock('@/lib/api', () => ({ ...jest.requireActual('@/lib/api'), api: jest.fn() }));
jest.mock('@/context/auth', () => ({ useAuth: jest.fn() }));

const anna: User = {
  id: 1,
  email: 'anna@example.com',
  first_name: 'Anna',
  last_name: '',
  is_email_verified: true,
  date_joined: '2026-10-01T12:00:00Z',
  shop_limit: 3,
};

function signedIn(user: User | null, actions: Record<string, jest.Mock> = {}) {
  (useAuth as jest.Mock).mockReturnValue({ user, ...actions });
}

const renderScreen = (screenElement: React.ReactElement) => render(screenElement, { wrapper: NotificationsProvider });

beforeEach(() => jest.clearAllMocks());

describe('sign in', () => {
  test('signs in with the trimmed e-mail', async () => {
    const signIn = jest.fn(async () => {});
    signedIn(null, { signIn });
    await renderScreen(<SignInScreen />);

    expect(screen.getByRole('button', { name: 'Zaloguj się' })).toBeDisabled();
    await fireEvent.changeText(screen.getByLabelText('E-mail'), ' anna@example.com ');
    await fireEvent.changeText(screen.getByLabelText('Hasło'), 'Sekretne-haslo-123');
    await fireEvent.press(screen.getByRole('button', { name: 'Zaloguj się' }));

    expect(signIn).toHaveBeenCalledWith('anna@example.com', 'Sekretne-haslo-123');
    expect(await screen.findByText('Zalogowano. Twoje sklepy są na miejscu.')).toBeTruthy();
  });

  test('wrong credentials get a plain message', async () => {
    signedIn(null, { signIn: jest.fn(async () => Promise.reject(new ApiError(401, { detail: 'No active account' }))) });
    await renderScreen(<SignInScreen />);

    await fireEvent.changeText(screen.getByLabelText('E-mail'), 'anna@example.com');
    await fireEvent.changeText(screen.getByLabelText('Hasło'), 'zle');
    await fireEvent.press(screen.getByRole('button', { name: 'Zaloguj się' }));

    expect(await screen.findByText('Nieprawidłowy e-mail lub hasło.')).toBeTruthy();
  });

  test('links to signing up', async () => {
    signedIn(null, { signIn: jest.fn() });
    await renderScreen(<SignInScreen />);

    await fireEvent.press(screen.getByRole('button', { name: 'Nie masz konta? Załóż je' }));

    expect(router.push).toHaveBeenCalledWith('/sign-up');
  });
});

describe('sign up', () => {
  test('creates the account and says where the code went', async () => {
    signedIn(null, { signUp: jest.fn(async () => {}) });
    await renderScreen(<SignUpScreen />);

    await fireEvent.changeText(screen.getByLabelText('E-mail'), 'Anna@Example.com');
    await fireEvent.changeText(screen.getByLabelText('Hasło'), 'Sekretne-haslo-123');
    await fireEvent.press(screen.getByRole('button', { name: 'Załóż konto' }));

    expect(await screen.findByText('Konto założone. Kod potwierdzający wysłaliśmy na anna@example.com.')).toBeTruthy();
  });

  test('shows what is wrong with the fields', async () => {
    const error = new ApiError(400, { password: ['To hasło jest zbyt powszechne.'] });
    signedIn(null, { signUp: jest.fn(async () => Promise.reject(error)) });
    await renderScreen(<SignUpScreen />);

    await fireEvent.changeText(screen.getByLabelText('E-mail'), 'anna@example.com');
    await fireEvent.changeText(screen.getByLabelText('Hasło'), 'haslo123');
    await fireEvent.press(screen.getByRole('button', { name: 'Załóż konto' }));

    expect(await screen.findByText('To hasło jest zbyt powszechne.')).toBeTruthy();
  });
});

describe('verify e-mail', () => {
  test('takes only six digits and confirms the address', async () => {
    const verifyEmail = jest.fn(async () => {});
    signedIn({ ...anna, is_email_verified: false }, { verifyEmail, resendCode: jest.fn(), signOut: jest.fn() });
    await renderScreen(<VerifyEmailScreen />);

    await fireEvent.changeText(screen.getByLabelText('Kod z wiadomości'), '12a-34 567');
    await fireEvent.press(screen.getByRole('button', { name: 'Potwierdź' }));

    expect(verifyEmail).toHaveBeenCalledWith('123456');
    expect(await screen.findByText('Adres e-mail potwierdzony. Możesz założyć pierwszy sklep.')).toBeTruthy();
  });

  test('a wrong code is reported', async () => {
    const verifyEmail = jest.fn(async () => Promise.reject(new ApiError(400, { detail: 'Nieprawidłowy kod.' })));
    signedIn({ ...anna, is_email_verified: false }, { verifyEmail, resendCode: jest.fn(), signOut: jest.fn() });
    await renderScreen(<VerifyEmailScreen />);

    await fireEvent.changeText(screen.getByLabelText('Kod z wiadomości'), '000000');
    await fireEvent.press(screen.getByRole('button', { name: 'Potwierdź' }));

    expect(await screen.findByText('Nieprawidłowy kod.')).toBeTruthy();
  });

  test('a new code can be sent after a minute, and another account used', async () => {
    jest.useFakeTimers();
    try {
      const resendCode = jest.fn(async () => {});
      const signOut = jest.fn(async () => {});
      signedIn({ ...anna, is_email_verified: false }, { verifyEmail: jest.fn(), resendCode, signOut });
      await renderScreen(<VerifyEmailScreen />);

      expect(screen.getByRole('button', { name: 'Wyślij kod ponownie za 60 s' })).toBeDisabled();
      for (let second = 0; second < 60; second++) await act(() => jest.advanceTimersByTimeAsync(1000));
      await fireEvent.press(screen.getByRole('button', { name: 'Wyślij kod ponownie' }));

      expect(resendCode).toHaveBeenCalled();
      expect(screen.getByText('Wysłaliśmy nowy kod na anna@example.com.')).toBeTruthy();

      await fireEvent.press(screen.getByRole('button', { name: 'Użyj innego konta' }));
      expect(signOut).toHaveBeenCalled();
    } finally {
      jest.useRealTimers();
    }
  });
});

describe('shop list', () => {
  const shop = (id: number, status: Shop['status']): Shop => ({
    id,
    name: `Sklep ${id}`,
    slug: `sklep-${id}`,
    url: `http://sklep-${id}.localhost`,
    status,
    status_display: status,
    created_at: '2026-11-01T10:00:00Z',
  });

  test('invites to open the first shop', async () => {
    signedIn(anna);
    mockApi({ 'GET /shops/': [[]] });
    await renderScreen(<ShopsScreen />);

    expect(await screen.findByText('Twój pierwszy sklep czeka na otwarcie')).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Załóż pierwszy sklep' }));
    expect(router.push).toHaveBeenCalledWith('/shops/new');
  });

  test('counts the shops and greets by name', async () => {
    signedIn(anna);
    mockApi({ 'GET /shops/': [[shop(1, 'active'), shop(2, 'failed')]] });
    await renderScreen(<ShopsScreen />);

    expect(await screen.findByText(/2 sklepy, w tym 1 otwarty\./)).toBeTruthy();
    expect(screen.getByText('Dzień dobry, Anna')).toBeTruthy();
    expect(screen.getByText('Sklep 2')).toBeTruthy();
  });

  test('says when the shop limit is reached', async () => {
    signedIn(anna);
    mockApi({ 'GET /shops/': [[shop(1, 'active'), shop(2, 'active'), shop(3, 'active')]] });
    await renderScreen(<ShopsScreen />);

    expect(await screen.findByText(/To limit na jedno konto\./)).toBeTruthy();
  });

  test('shows why the list did not load', async () => {
    signedIn(anna);
    mockApi({ 'GET /shops/': new ApiError(0, null) });
    await renderScreen(<ShopsScreen />);

    expect(await screen.findByText('Brak połączenia z serwerem.')).toBeTruthy();
  });
});

describe('account', () => {
  test('saves the name once it changes', async () => {
    const updateProfile = jest.fn(async () => {});
    signedIn(anna, { updateProfile, signOut: jest.fn() });
    await renderScreen(<AccountScreen />);

    expect(screen.getByRole('button', { name: 'Zapisz zmiany' })).toBeDisabled();
    await fireEvent.changeText(screen.getByLabelText('Nazwisko'), ' Nowak ');
    await fireEvent.press(screen.getByRole('button', { name: 'Zapisz zmiany' }));

    expect(updateProfile).toHaveBeenCalledWith({ first_name: 'Anna', last_name: 'Nowak' });
    expect(await screen.findByText('Zapisano zmiany w profilu.')).toBeTruthy();
  });

  test('a failed save is reported', async () => {
    signedIn(anna, { updateProfile: jest.fn(async () => Promise.reject(new Error('boom'))), signOut: jest.fn() });
    await renderScreen(<AccountScreen />);

    await fireEvent.changeText(screen.getByLabelText('Imię'), 'Ania');
    await fireEvent.press(screen.getByRole('button', { name: 'Zapisz zmiany' }));

    expect(await screen.findByText('Nie udało się zapisać zmian.')).toBeTruthy();
  });

  test('signs out and links to help pages', async () => {
    const signOut = jest.fn(async () => {});
    signedIn(anna, { updateProfile: jest.fn(), signOut });
    await renderScreen(<AccountScreen />);

    await fireEvent.press(screen.getByRole('link', { name: /Kontakt/ }));
    await fireEvent.press(screen.getByRole('button', { name: 'Wyloguj się' }));

    expect(router.push).toHaveBeenCalledWith('/contact');
    expect(signOut).toHaveBeenCalled();
    expect(await screen.findByText('Wylogowano.')).toBeTruthy();
  });
});

describe('contact', () => {
  test('sends the message with the signed-in user filled in', async () => {
    signedIn(anna);
    const api = mockApi({ 'POST /contact/': null });
    await renderScreen(<ContactScreen />);

    await fireEvent.changeText(screen.getByLabelText('Wiadomość'), 'Jak dodać zdjęcia?');
    await fireEvent.press(screen.getByRole('button', { name: 'Wyślij wiadomość' }));

    expect(api.sent('POST /contact/')).toEqual([
      { name: 'Anna', email: 'anna@example.com', topic: 'question', message: 'Jak dodać zdjęcia?' },
    ]);
    expect(await screen.findByText('Odpowiemy na adres anna@example.com.')).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Napisz kolejną wiadomość' }));
    expect(screen.getByLabelText('Wiadomość')).toHaveDisplayValue('');
  });

  test('too many messages get a clear answer, field errors show under fields', async () => {
    signedIn(null);
    mockApi({
      'POST /contact/': [new ApiError(400, { email: ['Podaj poprawny adres e-mail.'] }), new ApiError(429, null)],
    });
    await renderScreen(<ContactScreen />);
    expect(screen.getByRole('button', { name: 'Wyślij wiadomość' })).toBeDisabled();

    await fireEvent.changeText(screen.getByLabelText('Imię i nazwisko'), 'Jan');
    await fireEvent.changeText(screen.getByLabelText('E-mail do odpowiedzi'), 'jan@');
    await fireEvent.changeText(screen.getByLabelText('Wiadomość'), 'Mam pytanie o sklep.');
    await fireEvent.press(screen.getByRole('button', { name: 'Wyślij wiadomość' }));
    expect(await screen.findByText('Podaj poprawny adres e-mail.')).toBeTruthy();

    await fireEvent.press(screen.getByRole('button', { name: 'Wyślij wiadomość' }));
    expect(await screen.findByText('Wysłano już kilka wiadomości. Spróbuj za godzinę.')).toBeTruthy();
  });
});
