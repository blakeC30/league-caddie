/**
 * Auth store — global authentication state via Zustand.
 *
 * Holds the access token (in memory, never localStorage) and the current
 * user profile. The refresh token lives in an httpOnly cookie managed by
 * the browser, so it never touches this store.
 *
 * On hard refresh the token is lost, but the interceptor in client.ts will
 * automatically attempt a /auth/refresh via the cookie before any 401 fails.
 */

import { create } from "zustand";
import type { User } from "../types";

interface AuthState {
  token: string | null;
  user: User | null;
  setAuth: (user: User, token: string) => void;
  setToken: (token: string) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,

  setAuth: (user, token) => set({ user, token }),

  // Used by the refresh interceptor to update just the token.
  setToken: (token) => set({ token }),

  clearAuth: () => set({ token: null, user: null }),
}));
