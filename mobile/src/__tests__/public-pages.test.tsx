import { fireEvent, render, screen } from '@testing-library/react-native';

import HelpScreen from '@/app/(tabs)/help';
import AboutScreen from '@/app/about';
import HomeScreen from '@/app/index';
import { Faq } from '@/constants/content';
import { useAuth } from '@/context/auth';
import { NotificationsProvider } from '@/context/notifications';
import { router } from '@/testing/router';

jest.mock('expo-router', () => require('@/testing/router'));
jest.mock('@/context/auth', () => ({ useAuth: jest.fn() }));

const signedIn = (user: object | null) => (useAuth as jest.Mock).mockReturnValue({ user });
const renderScreen = (screenElement: React.ReactElement) => render(screenElement, { wrapper: NotificationsProvider });

beforeEach(() => jest.clearAllMocks());

test('the home page invites visitors to sign up', async () => {
  signedIn(null);
  await renderScreen(<HomeScreen />);

  expect(screen.getByText('Co dostajesz w każdym sklepie')).toBeTruthy();
  expect(screen.getByText('Trzy kroki do otwarcia')).toBeTruthy();
  await fireEvent.press(screen.getAllByRole('button', { name: 'Załóż konto' })[0]);
  await fireEvent.press(screen.getByRole('button', { name: 'Zobacz, jak to działa' }));

  expect(router.push).toHaveBeenCalledWith('/sign-up');
  expect(router.push).toHaveBeenCalledWith('/about');
});

test('the home page takes signed-in users to their shops', async () => {
  signedIn({ email: 'anna@example.com', shop_limit: 3, is_email_verified: true });
  await renderScreen(<HomeScreen />);

  await fireEvent.press(screen.getAllByRole('button', { name: 'Moje sklepy' })[0]);

  expect(router.push).toHaveBeenCalledWith('/shops');
});

test('the questions open one at a time', async () => {
  signedIn(null);
  await renderScreen(<AboutScreen />);
  const [first, second] = Faq;

  await fireEvent.press(screen.getByRole('button', { name: first.question }));
  expect(screen.getByRole('button', { name: first.question })).toHaveProp('accessibilityState', { expanded: true });

  await fireEvent.press(screen.getByRole('button', { name: second.question }));
  expect(screen.getByRole('button', { name: first.question })).toHaveProp('accessibilityState', { expanded: false });
  expect(screen.getByRole('button', { name: second.question })).toHaveProp('accessibilityState', { expanded: true });
});

test('the about page leads to the contact form', async () => {
  signedIn(null);
  await renderScreen(<AboutScreen />);

  await fireEvent.press(screen.getAllByRole('button', { name: 'Napisz do nas' })[0]);

  expect(router.push).toHaveBeenCalledWith('/contact');
});

test('help leads to the contact form too', async () => {
  signedIn({ email: 'anna@example.com' });
  await renderScreen(<HelpScreen />);

  await fireEvent.press(screen.getByRole('button', { name: 'Napisz do nas' }));

  expect(router.push).toHaveBeenCalledWith('/contact');
});
