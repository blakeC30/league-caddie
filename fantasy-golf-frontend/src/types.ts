/**
 * Shared domain types used across both the API layer and the auth store.
 *
 * Keeping these here breaks the circular dependency:
 *   store/authStore → api/endpoints → api/client → store/authStore
 *
 * authStore imports User from here; endpoints re-exports it from here.
 * client.ts can import from authStore without forming a cycle.
 */

export interface User {
  id: string;
  email: string;
  display_name: string;
  is_platform_admin: boolean;
  pick_reminders_enabled: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}
