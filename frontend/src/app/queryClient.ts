import { QueryClient } from "@tanstack/react-query";
import { retryTransient } from "../api/client";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        // Retry once only when the server was unreachable or failed; 4xx errors are final.
        retry: retryTransient,
        // Short fixed delay so an unavailable server is reported quickly.
        retryDelay: 300,
      },
    },
  });
}
