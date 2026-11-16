/**
 * Stand-in for expo-router in screen tests: `jest.mock('expo-router', () => require('@/testing/router'))`.
 * Set the screen's route params with `useLocalSearchParams.mockReturnValue(...)`.
 */
import { cloneElement, createElement, isValidElement, useEffect, type ReactElement, type ReactNode } from 'react';
import { Text } from 'react-native';

export const router = {
  push: jest.fn(),
  replace: jest.fn(),
  back: jest.fn(),
  dismissTo: jest.fn(),
  setParams: jest.fn(),
  canGoBack: jest.fn(() => true),
};

export const useLocalSearchParams = jest.fn(() => ({}));

// Screens are always focused in tests, so a focus effect runs like a mount effect.
export function useFocusEffect(effect: () => void | (() => void)) {
  useEffect(effect, [effect]);
}

export const Stack = { Screen: () => null };

export const usePathname = jest.fn(() => '/');

type LinkProps = { href: unknown; asChild?: boolean; children?: ReactNode; [prop: string]: unknown };

/** Pressing it calls `router.push(href)`, so tests can check where a link leads. */
export function Link({ href, asChild, children, ...rest }: LinkProps) {
  const onPress = () => router.push(href);
  if (asChild && isValidElement(children)) {
    const child = children as ReactElement<Record<string, unknown>>;
    // Like the real Link: an array of styles on the child is an error (StyleSheet.flatten it).
    if (Array.isArray(child.props.style)) {
      throw new Error('expo-router: Link asChild was given an array of styles; flatten them.');
    }
    return cloneElement(child, { ...rest, onPress });
  }
  return createElement(Text, { ...rest, onPress, accessibilityRole: 'link' }, children);
}

/** Navigates on render, like expo-router's Redirect. */
export function Redirect({ href }: { href: unknown }) {
  useEffect(() => {
    router.replace(href);
  }, [href]);
  return null;
}
