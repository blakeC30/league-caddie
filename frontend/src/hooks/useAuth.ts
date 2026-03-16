/**
 * useAuth — authentication actions and state.
 *
 * Wraps the auth store and API calls so components never touch axios directly.
 * On mount, attempts a silent token refresh so users stay logged in after a
 * hard page reload (the httpOnly refresh cookie is still valid).
 */

import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { authApi, usersApi } from "../api/endpoints";
import { useAuthStore } from "../store/authStore";

export function useAuth() {
  const { token, user, setAuth, clearAuth } = useAuthStore();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [bootstrapping, setBootstrapping] = useState(!token);

  // Destination after successful login/register. Falls back to /leagues.
  const next = searchParams.get("next") ?? "/leagues";

  // On first mount with no token: try to restore the session from the
  // httpOnly refresh-token cookie. This handles hard refreshes.
  useEffect(() => {
    if (token) {
      setBootstrapping(false);
      return;
    }
    authApi
      .refresh()
      .then(({ access_token }) => {
        // Store the token BEFORE calling me() so the request interceptor
        // can attach it as a Bearer header. Without this, me() gets a 401,
        // the refresh interceptor fires again, fails, and force-reloads the page.
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
      clearAuth();
      navigate("/login");
    }
  }

  return { token, user, bootstrapping, login, loginWithGoogle, register, logout };
}
