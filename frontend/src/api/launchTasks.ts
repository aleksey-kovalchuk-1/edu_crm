import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "./client";
import type { TaskPriority, TaskStatus } from "./tasks";

/** One task in an Interaction's plan, as returned by GET /launches/{id}/tasks. */
export interface LaunchTask {
  id: number;
  title: string;
  status: TaskStatus;
  priority: TaskPriority;
  deadline: string | null;
  assignee: { id: number; full_name: string } | null;
  is_optional: boolean;
}

export interface LaunchTaskCategory {
  index: number;
  name: string;
  tasks: LaunchTask[];
  /** Count of unfinished tasks — the backend only counts this for categories earlier than
   * `current_category`; it is always 0 for the current and later categories. */
  unfinished_count: number;
}

export interface LaunchTasksResponse {
  current_category: number;
  categories: LaunchTaskCategory[];
  uncategorized: LaunchTask[];
}

export const useLaunchTasks = (launchId: number) =>
  useQuery({
    queryKey: ["launches", launchId, "tasks"],
    queryFn: () => apiRequest<LaunchTasksResponse>(`/launches/${launchId}/tasks`),
  });
