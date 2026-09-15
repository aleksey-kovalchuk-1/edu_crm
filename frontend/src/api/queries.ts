import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { apiRequest } from "./client";
import type {
  Dashboard,
  Launch,
  LaunchInput,
  StageEvent,
  Task,
  University,
  UniversityInput,
} from "./types";

/** Stable query keys; one per endpoint. */
export const queryKeys = {
  universities: ["universities"] as const,
  launches: ["launches"] as const,
  tasks: ["tasks"] as const,
  stages: ["stages"] as const,
  dashboard: ["dashboard"] as const,
  launchHistory: (id: number) => ["launch-history", id] as const,
};

export const useUniversities = () =>
  useQuery({
    queryKey: queryKeys.universities,
    queryFn: () => apiRequest<University[]>("/universities"),
  });

export const useLaunches = () =>
  useQuery({
    queryKey: queryKeys.launches,
    queryFn: () => apiRequest<Launch[]>("/launches"),
  });

export const useTasks = () =>
  useQuery({
    queryKey: queryKeys.tasks,
    queryFn: () => apiRequest<Task[]>("/tasks"),
  });

export const useStages = () =>
  useQuery({
    queryKey: queryKeys.stages,
    queryFn: () => apiRequest<string[]>("/stages"),
    staleTime: Infinity,
  });

export const useDashboard = () =>
  useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: () => apiRequest<Dashboard>("/dashboard"),
  });

export const useLaunchHistory = (id: number) =>
  useQuery({
    queryKey: queryKeys.launchHistory(id),
    queryFn: () => apiRequest<StageEvent[]>(`/launches/${id}/history`),
  });

/**
 * Mark queries stale and refetch the active ones in the background. Not
 * awaited, so a mutation stops being pending as soon as the server answers.
 */
const invalidate = (client: QueryClient, ...keys: (readonly unknown[])[]) => {
  for (const queryKey of keys)
    void client.invalidateQueries({ queryKey, exact: true });
};

/** Toggle a task; optimistic, then refreshes tasks only (the dashboard does not count tasks). */
export function useToggleTask() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, done }: { id: number; done: boolean }) =>
      apiRequest<Task>(`/tasks/${id}`, "PATCH", { done }),
    onMutate: async ({ id, done }) => {
      await client.cancelQueries({ queryKey: queryKeys.tasks, exact: true });
      const previous = client.getQueryData<Task[]>(queryKeys.tasks);
      client.setQueryData<Task[]>(queryKeys.tasks, (tasks) =>
        tasks?.map((t) => (t.id === id ? { ...t, done } : t)),
      );
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous)
        client.setQueryData(queryKeys.tasks, context.previous);
    },
    onSettled: () => invalidate(client, queryKeys.tasks),
  });
}

/** Change a launch stage; optimistic, then refreshes launches, its history and dashboard. */
export function useChangeStage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, stage }: { id: number; stage: number }) =>
      apiRequest<Launch>(`/launches/${id}`, "PATCH", { stage }),
    onMutate: async ({ id, stage }) => {
      await client.cancelQueries({ queryKey: queryKeys.launches, exact: true });
      const previous = client.getQueryData<Launch[]>(queryKeys.launches);
      client.setQueryData<Launch[]>(queryKeys.launches, (launches) =>
        launches?.map((l) => (l.id === id ? { ...l, stage } : l)),
      );
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous)
        client.setQueryData(queryKeys.launches, context.previous);
    },
    onSettled: (_data, _error, { id }) =>
      invalidate(
        client,
        queryKeys.launches,
        queryKeys.launchHistory(id),
        queryKeys.dashboard,
      ),
  });
}

export function useCreateUniversity() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: UniversityInput) =>
      apiRequest<University>("/universities", "POST", data),
    onSuccess: () =>
      invalidate(client, queryKeys.universities, queryKeys.dashboard),
  });
}

export function useCreateLaunch() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: LaunchInput) =>
      apiRequest<Launch>("/launches", "POST", data),
    onSuccess: () => invalidate(client, queryKeys.launches, queryKeys.dashboard),
  });
}
