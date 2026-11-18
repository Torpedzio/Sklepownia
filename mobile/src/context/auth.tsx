import { createContext, use, useEffect, useState, type PropsWithChildren } from 'react';

import { useNotify } from '@/context/notifications';
import { api, ApiError, loadTokens, setOnSessionExpired, setTokens } from '@/lib/api';
import { avatarForm, type AvatarFile } from '@/lib/avatar';
import { forgetDevice, registerDevice } from '@/lib/push';
import type { Tokens, User } from '@/lib/types';

type AuthContextValue = {
  isLoading: boolean;
  user: User | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  verifyEmail: (code: string) => Promise<void>;
  resendCode: () => Promise<void>;
  updateProfile: (changes: Pick<User, 'first_name' | 'last_name'>) => Promise<void>;
  /** Loads the account again, e.g. after paying for a plan. */
  refreshUser: () => Promise<void>;
  /** Uploads a new profile picture; the server crops it to a square. */
  changeAvatar: (file: AvatarFile) => Promise<void>;
  removeAvatar: () => Promise<void>;
  /** New password; other devices are signed out, this one keeps working with fresh tokens. */
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  /** Signs out on every device, this one included. */
  signOutEverywhere: () => Promise<void>;
  /** E-mails a code for a new password; the server answers the same for addresses without an account. */
  requestPasswordReset: (email: string) => Promise<void>;
  /** Sets the new password with the code from the e-mail and signs in. */
  resetPassword: (email: string, code: string, newPassword: string) => Promise<void>;
  /** Deletes the account with its shops and plan for good, then forgets the session here. */
  deleteAccount: (password: string) => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [isLoading, setIsLoading] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const notify = useNotify();

  useEffect(() => {
    setOnSessionExpired(() => {
      setUser(null);
      notify.error('Sesja wygasła. Zaloguj się ponownie.');
    });
    (async () => {
      try {
        if (await loadTokens()) setUser(await api<User>('/auth/me/'));
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) await setTokens(null);
      } finally {
        setIsLoading(false);
      }
    })();
  }, [notify]);

  const value: AuthContextValue = {
    isLoading,
    user,
    async signIn(email, password) {
      const tokens = await api<Tokens>('/auth/login/', { method: 'POST', body: { email, password }, auth: false });
      await setTokens(tokens);
      setUser(await api<User>('/auth/me/'));
    },
    async signUp(email, password) {
      const data = await api<{ user: User; tokens: Tokens }>('/auth/register/', {
        method: 'POST',
        body: { email, password },
        auth: false,
      });
      await setTokens(data.tokens);
      setUser(data.user);
    },
    async signOut() {
      const tokens = await loadTokens();
      if (tokens) {
        // While still signed in: the phone stops getting this account's notifications.
        await forgetDevice();
        await api('/auth/logout/', { method: 'POST', body: { refresh: tokens.refresh } }).catch(() => {});
      }
      await setTokens(null);
      setUser(null);
    },
    async verifyEmail(code) {
      setUser(await api<User>('/auth/verify-email/', { method: 'POST', body: { code } }));
    },
    async resendCode() {
      await api('/auth/resend-verification/', { method: 'POST' });
    },
    async updateProfile(changes) {
      setUser(await api<User>('/auth/me/', { method: 'PATCH', body: changes }));
    },
    async refreshUser() {
      setUser(await api<User>('/auth/me/'));
    },
    async changeAvatar(file) {
      setUser(await api<User>('/auth/avatar/', { method: 'PUT', body: avatarForm(file) }));
    },
    async removeAvatar() {
      setUser(await api<User>('/auth/avatar/', { method: 'DELETE' }));
    },
    async changePassword(currentPassword, newPassword) {
      const tokens = await api<Tokens>('/auth/change-password/', {
        method: 'POST',
        body: { current_password: currentPassword, new_password: newPassword },
      });
      await setTokens(tokens);
      // Changing the password signs out every phone, this one's notifications included; it gets them back.
      await registerDevice({ force: true }).catch(() => {});
    },
    async signOutEverywhere() {
      await api('/auth/logout-everywhere/', { method: 'POST' });
      await setTokens(null);
      setUser(null);
    },
    async requestPasswordReset(email) {
      await api('/auth/password-reset/', { method: 'POST', body: { email }, auth: false });
    },
    async resetPassword(email, code, newPassword) {
      const tokens = await api<Tokens>('/auth/password-reset/confirm/', {
        method: 'POST',
        body: { email, code, new_password: newPassword },
        auth: false,
      });
      await setTokens(tokens);
      setUser(await api<User>('/auth/me/'));
    },
    async deleteAccount(password) {
      await api('/auth/delete-account/', { method: 'POST', body: { password } });
      await setTokens(null);
      setUser(null);
    },
  };

  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth() {
  const context = use(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
