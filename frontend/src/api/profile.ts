import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import { authKeys, type Session } from "./auth";

/* Types of backend/app/profile_routes.py */

export interface PhoneRequestResponse {
  expires_in: number;
}

export interface PhoneVerifyResponse {
  phone: string;
  phone_verified_at: string | null;
}

/** Client-side mirror of the server's accepted formats (server validation is authoritative). */
export function isPlausiblePhone(raw: string): boolean {
  const digits = raw.replace(/\D/g, "");
  return digits.length === 11 && (digits[0] === "7" || digits[0] === "8");
}

/** POST /profile/phone: request a code for the acting user's own account. */
export function useRequestPhoneCode() {
  return useMutation({
    mutationFn: (phone: string) =>
      apiRequest<PhoneRequestResponse>("/profile/phone", "POST", { phone }),
  });
}

/**
 * POST /profile/phone/verify. On success, updates the cached session in place so the rest of
 * the interface (and this page) sees the new phone/verified state without a separate fetch.
 */
export function useVerifyPhoneCode() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (code: string) =>
      apiRequest<PhoneVerifyResponse>("/profile/phone/verify", "POST", { code }),
    onSuccess: (data) => {
      client.setQueryData<Session>(authKeys.me, (session) =>
        session && {
          ...session,
          user: {
            ...session.user,
            phone: data.phone,
            phone_verified_at: data.phone_verified_at,
          },
        },
      );
    },
  });
}
