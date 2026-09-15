import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "../api/client";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        // Retry once only when the server was unreachable or failed; 4xx errors are final.
        retry: (failureCount, error) =>
          failureCount < 1 &&
          error instanceof ApiError &&
          (error.status === 0 || error.status >= 500),
        // Short fixed delay so an unavailable server is reported quickly.
        retryDelay: 300,
      },
    },
  });
}
