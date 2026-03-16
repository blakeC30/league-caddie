/**
 * Axios instance shared across all API calls.
 *
 * Responsibilities:
 *  1. Set base URL so every call goes to /api/v1/...
 *     In dev, Vite proxies /api → http://localhost:8000, so no CORS.
 *     In prod, nginx routes /api → the backend service.
 *  2. Attach the JWT access token from the auth store on every request.
 *  3. On 401: attempt one silent refresh via the httpOnly cookie, then
 *     retry the original request. If refresh fails, clear auth and redirect
 *     to /login so the user can re-authenticate.
 */

import axios from "axios";
import { useAuthStore } from "../store/authStore";

export const api = axios.create({
  baseURL: "/api/v1",
  withCredentials: true, // send httpOnly refresh-token cookie on every request
  timeout: 30_000,       // 30 s — surface hung requests as errors instead of hanging forever
});

// --- Request interceptor: attach access token ---
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// --- Response interceptor: silent token refresh on 401 ---
//
// refreshPromise acts as a shared lock. All concurrent 401s await the same
// promise rather than racing to call /auth/refresh. This is safe across
// multiple in-flight requests within one tab (cross-tab isolation is handled
// by the backend: the refresh token cookie is httpOnly and single-use, so
// whichever tab wins the race gets a new token and the other sees a 401 on
// the refresh call itself, which triggers clearAuth + redirect).
let refreshPromise: Promise<string> | null = null;

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;

    // Only attempt refresh on 401 and only once per request.
    if (error.response?.status !== 401 || original._retried) {
      return Promise.reject(error);
    }
    original._retried = true;

    // If a refresh is already in flight, piggyback on it instead of starting
    // a second one. All callers await the same promise and get the same token.
    if (!refreshPromise) {
      refreshPromise = axios
        .post("/api/v1/auth/refresh", {}, { withCredentials: true })
        .then(({ data }) => {
          const newToken: string = data.access_token;
          useAuthStore.getState().setToken(newToken);
          return newToken;
        })
        .finally(() => {
          refreshPromise = null;
        });
    }

    try {
      const newToken = await refreshPromise;
      original.headers.Authorization = `Bearer ${newToken}`;
      return api(original);
    } catch (refreshErr) {
      useAuthStore.getState().clearAuth();
      // Only redirect if we're not already on a public page. Redirecting to
      // /login from /login causes a full browser reload and an infinite loop.
      const publicPaths = ["/login", "/register", "/join"];
      const onPublicPage = publicPaths.some((p) =>
        window.location.pathname.startsWith(p)
      );
      if (!onPublicPage) {
        window.location.href = "/login";
      }
      return Promise.reject(refreshErr);
    }
  }
);
