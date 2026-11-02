import { createContext, use, useEffect, useState, type PropsWithChildren } from 'react';

import { api, ApiError, loadTokens, setOnSessionExpired, setTokens } from '@/lib/api';
import type { Tokens, User } from '@/lib/types';

type AuthContextValue = {
  isLoading: boolean;
  user: User | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  verifyEmail: (code: string) => Promise<void>;
  resendCode: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [isLoading, setIsLoading] = useState(true);
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    setOnSessionExpired(() => setUser(null));
    (async () => {
      try {
        if (await loadTokens()) setUser(await api<User>('/auth/me/'));
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) await setTokens(null);
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

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
  };

  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth() {
  const context = use(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
