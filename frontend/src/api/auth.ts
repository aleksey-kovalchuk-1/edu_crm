import { useMutation, useQuery } from "@tanstack/react-query";
import { browser } from "../lib/browser";
import {
  API_BASE,
  AUTH_ME_PATH,
  ApiError,
  apiRequest,
  retryTransient,
} from "./client";

export interface CurrentUser {
  id: number;
  email: string;
  full_name: string;
  roles: string[];
  /** CRM-owned phone verification (D-161): "" until a number is verified. */
  phone: string;
  phone_verified_at: string | null;
}

/** Response of GET /auth/me. */
export interface Session {
  user: CurrentUser;
  csrf_token: string;
}

export const authKeys = {
  me: ["auth", "me"] as const,
};

/** An in-app path starting with exactly one "/" and without backslashes; otherwise "/". */
export const safeNextPath = (path: string) =>
  /^\/(?!\/)/.test(path) && !path.includes("\\") ? path : "/";

/** Backend login start; a full-page navigation, never fetch. */
export const loginUrl = (next: string) =>
  `${API_BASE}/auth/login?next=${encodeURIComponent(safeNextPath(next))}`;

/** Backend registration start (Keycloak's hosted registration page); a full-page navigation, never fetch. */
export const registerUrl = (next: string) =>
  `${API_BASE}/auth/register?next=${encodeURIComponent(safeNextPath(next))}`;

export const useCurrentUser = () =>
  useQuery({
    queryKey: authKeys.me,
    queryFn: () => apiRequest<Session>(AUTH_ME_PATH),
    // Short enough that roles and the CSRF token follow changes made in other tabs.
    staleTime: 60_000,
    refetchOnWindowFocus: true,
    // 401 is never retried (only network errors and 5xx are).
    retry: retryTransient,
  });

/**
 * True when the backend confirmed the logout and points back to the CRM start
 * page; otherwise the URL is Keycloak's end-session page the user must visit.
 */
export function isLocalLogoutTarget(url: string): boolean {
  try {
    return new URL(url, window.location.href).pathname === "/";
  } catch {
    return false;
  }
}

/** POST /auth/logout. A 401 means the session had already ended — also logged out. */
export function useLogout(onLoggedOut: () => void) {
  return useMutation({
    mutationFn: async () => {
      try {
        return await apiRequest<{ logout_url: string }>("/auth/logout", "POST");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401)
          return { logout_url: "/" };
        throw error;
      }
    },
    onSuccess: ({ logout_url }) => {
      if (isLocalLogoutTarget(logout_url)) onLoggedOut();
      else browser.assign(logout_url);
    },
  });
}
