import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";

/* Types of backend/app/notification_routes.py */

export interface NotificationItem {
  id: number;
  event_type: string;
  title: string;
  body: string;
  /** null when the linked record is no longer visible to the user. */
  link: { type: string; id: number; path: string } | null;
  created_at: string;
  read_at: string | null;
}

export interface EventPreference { key: string; label: string; enabled: boolean; default: boolean; }
export interface PreferenceGroup { key: string; label: string; events: EventPreference[]; }
export interface NotificationPreferences { groups: PreferenceGroup[]; paused_until: string | null; }
export type PauseDuration = "1h" | "tomorrow" | "1w" | "forever" | "off";

export const notificationKeys = {
  all: ["notifications"] as const,
  list: ["notifications", "list"] as const,
  count: ["notifications", "unread-count"] as const,
  preferences: ["notifications", "preferences"] as const,
};

/** Polled every 60 s so the bell reflects new notifications without a reload. */
export const useUnreadCount = () =>
  useQuery({
    queryKey: notificationKeys.count,
    queryFn: () => apiRequest<{ count: number }>("/notifications/unread-count"),
    refetchInterval: 60_000,
  });

export const useNotifications = (enabled: boolean) =>
  useQuery({
    queryKey: notificationKeys.list,
    queryFn: () => apiRequest<NotificationItem[]>("/notifications?limit=50"),
    enabled,
    // Always stale: every opening of the panel reloads it, so the list matches the badge.
    staleTime: 0,
  });

function useNotificationMutation<T = void>(fn: (vars: T) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => { void client.invalidateQueries({ queryKey: notificationKeys.all }); },
  });
}

export const useMarkRead = () =>
  useNotificationMutation((id: number) => apiRequest<void>(`/notifications/${id}/read`, "POST"));
export const useMarkAllRead = () =>
  useNotificationMutation(() => apiRequest<void>("/notifications/read-all", "POST"));

export const useNotificationPreferences = () =>
  useQuery({
    queryKey: notificationKeys.preferences,
    queryFn: () => apiRequest<NotificationPreferences>("/notifications/preferences"),
  });

export function useSavePreferences() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (preferences: Record<string, boolean>) =>
      apiRequest<NotificationPreferences>("/notifications/preferences", "PUT", { preferences }),
    onSuccess: (data) => client.setQueryData(notificationKeys.preferences, data),
  });
}

export function useSetPause() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (duration: PauseDuration) =>
      apiRequest<{ paused_until: string | null }>("/notifications/pause", "PUT", { duration }),
    onSuccess: ({ paused_until }) =>
      client.setQueryData<NotificationPreferences>(notificationKeys.preferences, (prefs) => prefs && { ...prefs, paused_until }),
  });
}
