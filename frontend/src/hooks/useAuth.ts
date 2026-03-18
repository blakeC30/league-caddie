/**
 * useAuth — authentication actions and state.
 *
 * Wraps the auth store and API calls so components never touch axios directly.
 * On mount, attempts a silent token refresh so users stay logged in after a
 * hard page reload (the httpOnly refresh cookie is still valid).
 *
 * Bootstrap cases handled on mount:
 *
 *   token && user   — fully authenticated; nothing to do.
 *
 *   token && !user  — token was set by the axios response interceptor (a 401
 *                     on a public page triggered a silent refresh) but the user
 *                     profile was never fetched. Call GET /users/me directly
 *                     with the existing token to complete the session.
 *                     This happens after the Stripe billing flow: BillingSuccess
 *                     makes API calls outside Layout, the interceptor refreshes
 *                     the token, and when the user navigates to the league page
 *                     Layout mounts with a token-but-no-user state.
 *
 *   !token          — no token at all; attempt a full silent refresh via the
 *                     httpOnly refresh-token cookie (handles hard reloads).
 *
 * bootstrapping starts true whenever the user profile is missing, so the
 * Layout spinner covers all three loading paths and prevents a flash of
 * blank display-name or a momentarily missing Manage button.
 */

import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { authApi, usersApi } from "../api/endpoints";
import { useAuthStore } from "../store/authStore";

export function useAuth() {
  const { token, user, setAuth, clearAuth } = useAuthStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();

  // Show the bootstrap spinner whenever the user profile is absent, regardless
  // of whether a token is already in the store. This covers the case where the
  // axios interceptor set the token without fetching the user profile.
  const [bootstrapping, setBootstrapping] = useState(!user);

  // Destination after successful login/register. Falls back to /leagues.
  const next = searchParams.get("next") ?? "/leagues";

  // On mount: ensure both token and user profile are populated before rendering.
  useEffect(() => {
    if (token && user) {
      // Fully authenticated — nothing to fetch.
      setBootstrapping(false);
      return;
    }

    if (token && !user) {
      // Token is present (set by the axios interceptor on a public page) but
      // the user profile was never fetched. Complete the session with a direct
      // GET /users/me — no refresh needed since the token is already valid.
      usersApi
        .me()
        .then((u) => setAuth(u, token))
        .catch(() => clearAuth())
        .finally(() => setBootstrapping(false));
      return;
    }

    // No token at all — attempt a full silent refresh via the httpOnly cookie.
    // Store the token BEFORE calling me() so the request interceptor can attach
    // it as a Bearer header. Without this, me() gets a 401, the refresh
    // interceptor fires again, fails, and force-reloads the page.
    authApi
      .refresh()
      .then(({ access_token }) => {
        useAuthStore.getState().setToken(access_token);
        return usersApi.me().then((u) => setAuth(u, access_token));
      })
      .catch(() => clearAuth())
      .finally(() => setBootstrapping(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function login(email: string, password: string) {
    const { access_token } = await authApi.login(email, password);
    useAuthStore.getState().setToken(access_token); // must be set before me()
    const me = await usersApi.me();
    setAuth(me, access_token);
    navigate(next);
  }

  async function loginWithGoogle(id_token: string) {
    const { access_token } = await authApi.google(id_token);
    useAuthStore.getState().setToken(access_token);
    const me = await usersApi.me();
    setAuth(me, access_token);
    navigate(next);
  }

  async function register(email: string, password: string, display_name: string) {
    const { access_token } = await authApi.register(email, password, display_name);
    useAuthStore.getState().setToken(access_token);
    const me = await usersApi.me();
    setAuth(me, access_token);
    navigate(next);
  }

  async function logout() {
    try {
      await authApi.logout();
    } finally {
      queryClient.clear();
      clearAuth();
      navigate("/login");
    }
  }

  return { token, user, bootstrapping, login, loginWithGoogle, register, logout };
}
