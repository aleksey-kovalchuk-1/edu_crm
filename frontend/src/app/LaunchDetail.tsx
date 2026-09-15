import { createContext, useContext, useState, type ReactNode } from "react";
import { LaunchDetailModal } from "../components/LaunchDetailModal";

const OpenLaunchContext = createContext<(id: number) => void>(() => {});

/** Holds the launch detail modal so any page can open it. */
export function LaunchDetailProvider({ children }: { children: ReactNode }) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  return (
    <OpenLaunchContext.Provider value={setSelectedId}>
      {children}
      {selectedId !== null && (
        <LaunchDetailModal
          key={selectedId}
          id={selectedId}
          close={() => setSelectedId(null)}
        />
      )}
    </OpenLaunchContext.Provider>
  );
}

export const useOpenLaunch = () => useContext(OpenLaunchContext);
