import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import { authKeys, type Session } from "./auth";

/* Types of backend/app/profile_routes.py */

export interface Profile {
  id: number;
  email: string;
  first_name: string;
  middle_name: string;
  last_name: string;
  full_name: string;
  phone: string;
  phone_verified_at: string | null;
  timezone: string;
  telegram: string;
  whatsapp: string;
  email_sender_identity_id: number | null;
}

export type ProfilePatch = Partial<
  Pick<Profile, "first_name" | "middle_name" | "last_name" | "timezone" | "telegram" | "whatsapp">
> & {
  /** 0 clears the selection. */
  email_sender_identity_id?: number;
};

export interface PhoneRequestResponse {
  expires_in: number;
}

export interface PhoneVerifyResponse {
  phone: string;
  phone_verified_at: string | null;
}

/** Saved Telegram/WhatsApp handles are contacts only: the CRM has no messaging integration. */
export function contactStatus(value: string): "Не указан" | "Сохранён · не подключён" {
  return value.trim() ? "Сохранён · не подключён" : "Не указан";
}

/** Client-side mirror of the server rule: a Russian mobile number (server validation is authoritative). */
export function isPlausiblePhone(raw: string): boolean {
  const digits = raw.replace(/\D/g, "");
  return digits.length === 11 && (digits[0] === "7" || digits[0] === "8") && digits[1] === "9";
}

export const profileKeys = { me: ["profile"] as const };

export const useProfile = () =>
  useQuery({ queryKey: profileKeys.me, queryFn: () => apiRequest<Profile>("/profile") });

function patchSession(client: ReturnType<typeof useQueryClient>, user: Partial<Session["user"]>) {
  client.setQueryData<Session>(authKeys.me, (session) => session && { ...session, user: { ...session.user, ...user } });
}

/** PATCH /profile. Never carries the phone: that changes only through SMS verification. */
export function useUpdateProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: ProfilePatch) => apiRequest<Profile>("/profile", "PATCH", data),
    onSuccess: (profile) => {
      client.setQueryData(profileKeys.me, profile);
      patchSession(client, {
        full_name: profile.full_name, first_name: profile.first_name, middle_name: profile.middle_name,
        last_name: profile.last_name, timezone: profile.timezone, telegram: profile.telegram, whatsapp: profile.whatsapp,
      });
    },
  });
}

/** POST /profile/phone: request a code for the acting user's own account. */
export function useRequestPhoneCode() {
  return useMutation({
    mutationFn: (phone: string) =>
      apiRequest<PhoneRequestResponse>("/profile/phone", "POST", { phone }),
  });
}

/**
 * POST /profile/phone/verify. On success, updates the cached session and profile in place so the rest
 * of the interface sees the new phone/verified state without a separate fetch.
 */
export function useVerifyPhoneCode() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (code: string) =>
      apiRequest<PhoneVerifyResponse>("/profile/phone/verify", "POST", { code }),
    onSuccess: (data) => {
      patchSession(client, { phone: data.phone, phone_verified_at: data.phone_verified_at });
      client.setQueryData<Profile>(profileKeys.me, (profile) => profile && { ...profile, ...data });
    },
  });
}
