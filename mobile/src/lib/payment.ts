import * as Linking from 'expo-linking';
import { router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { Platform } from 'react-native';

import type { Checkout } from '@/lib/types';

export function paymentReturnUrl() {
  return Linking.createURL('/billing/return');
}

/** The web leaves for the gateway and returns by redirect; phones open it in the system browser and go on once it closes. */
export async function goToPayment(checkout: Checkout) {
  if (Platform.OS === 'web') {
    globalThis.location.assign(checkout.redirect_url);
    return;
  }
  await WebBrowser.openAuthSessionAsync(checkout.redirect_url, paymentReturnUrl());
  // Closed or finished, the return screen asks the platform how the payment ended.
  router.replace({ pathname: '/billing/return', params: { payment: String(checkout.payment.id) } });
}
