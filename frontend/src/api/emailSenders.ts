import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import { profileKeys } from "./profile";

/* Types of backend/app/email_routes.py */

export type SenderStatus = "pending_approval" | "awaiting_confirmation" | "active" | "rejected";

export interface Sender {
  id: number;
  email_address: string;
  display_name: string;
  is_active: boolean;
  status: SenderStatus;
  is_shared: boolean;
  rejection_reason: string;
  usable: boolean;
}

export interface QueueItem extends Sender {
  requested_by: string;
  requested_at: string | null;
}

export interface Delivery {
  delivered: boolean;
  message: string;
}

export interface SenderRequest {
  email_address: string;
  display_name: string;
}

export const SENDER_STATUS_LABELS: Record<SenderStatus, string> = {
  pending_approval: "Ждёт одобрения",
  awaiting_confirmation: "Ждёт подтверждения по email",
  active: "Подтверждён",
  rejected: "Отклонён",
};

/** The queue key shares the ["email-senders"] prefix, so invalidating `all` refreshes both lists. */
export const senderKeys = {
  all: ["email-senders"] as const,
  mine: ["email-senders", "mine"] as const,
  queue: ["email-senders", "queue"] as const,
};

export const useSenders = () =>
  useQuery({ queryKey: senderKeys.mine, queryFn: () => apiRequest<Sender[]>("/email-senders") });

export const useSenderQueue = () =>
  useQuery({ queryKey: senderKeys.queue, queryFn: () => apiRequest<QueueItem[]>("/email-senders/queue") });

function useSenderMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: senderKeys.all });
      void client.invalidateQueries({ queryKey: profileKeys.me });
    },
  });
}

export const useRequestSender = () =>
  useSenderMutation((data: SenderRequest) => apiRequest<Sender>("/email-senders/requests", "POST", data));
export const useWithdrawRequest = () =>
  useSenderMutation((id: number) => apiRequest<void>(`/email-senders/requests/${id}`, "DELETE"));
export const useApproveSender = () =>
  useSenderMutation((id: number) => apiRequest<Delivery>(`/email-senders/${id}/approve`, "POST"));
export const useRejectSender = () =>
  useSenderMutation(({ id, reason }: { id: number; reason: string }) =>
    apiRequest<void>(`/email-senders/${id}/reject`, "POST", { reason }));
export const useResendConfirmation = () =>
  useSenderMutation((id: number) => apiRequest<Delivery>(`/email-senders/${id}/resend`, "POST"));
export const useCreateSharedSender = () =>
  useSenderMutation((data: SenderRequest) => apiRequest<Sender>("/email-senders", "POST", data));
export const useDeactivateSender = () =>
  useSenderMutation((id: number) => apiRequest<void>(`/email-senders/${id}`, "DELETE"));

export const useTestSend = () =>
  useMutation({ mutationFn: () => apiRequest<Delivery>("/email-senders/test", "POST") });

/** Public: called from the confirmation page outside AuthGate. */
export const useConfirmSender = () =>
  useMutation({
    mutationFn: (token: string) =>
      apiRequest<{ email_address: string }>("/email-senders/confirm", "POST", { token }),
  });
