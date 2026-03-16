/**
 * useAppConfig — fetches public platform feature flags from GET /config.
 *
 * Cached indefinitely for the session (staleTime: Infinity) since these flags
 * only change on a backend deploy, not at runtime.
 */

import { useQuery } from "@tanstack/react-query";
import { configApi } from "../api/endpoints";

export function useAppConfig() {
  return useQuery({
    queryKey: ["appConfig"],
    queryFn: configApi.get,
    staleTime: Infinity,
  });
}
