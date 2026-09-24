import { useEffect, useState } from "react";

/** Current time, refreshed every minute so relative times ("5 мин назад", "Сегодня") stay correct. */
export function useNow(intervalMs = 60_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}
