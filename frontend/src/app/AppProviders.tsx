import { useState, type ReactNode } from "react";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { authKeys, type Session } from "../api/auth";
import { configureApiClient } from "../api/client";
import { createQueryClient } from "./queryClient";

export function AppProviders({
  client,
  children,
}: {
  client?: QueryClient;
  children: ReactNode;
}) {
  const [queryClient] = useState(() => {
    const qc = client ?? createQueryClient();
    // Re-read /auth/me keeping cached data (the page stays mounted); joins an in-flight check.
    const refetchSession = () =>
      qc.refetchQueries(
        { queryKey: authKeys.me, exact: true },
        { cancelRefetch: false },
      );
    // Configured before any child query runs.
    configureApiClient({
      csrfToken: () => qc.getQueryData<Session>(authKeys.me)?.csrf_token,
      // AuthGate shows the "session expired" dialog only if /auth/me itself returns 401.
      onUnauthenticated: () => void refetchSession(),
      refreshSession: refetchSession,
    });
    return qc;
  });
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
