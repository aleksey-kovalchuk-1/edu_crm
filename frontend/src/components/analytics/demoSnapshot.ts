import type { AnalyticsSnapshot } from "../../api/analytics";

/** Clearly fictional preview, never sent to the API or included in a PDF. */
export function demoSnapshot(stageNames: string[]): Pick<AnalyticsSnapshot, "stages" | "monthly" | "ranking"> {
  const year = new Date().getFullYear();
  const counts = [5, 5, 5, 5, 2];
  return {
    stages: stageNames.map((name, index) => ({ name, count: counts[index] ?? 0 })),
    monthly: [0, 1, 2, 1, 2, 2].map((count, index) => ({
      month: `${year}-${String(index + 1).padStart(2, "0")}`, count,
    })),
    ranking: [3, 2, 1, 1, 1].map((programs, index) => ({
      id: index + 1, name: `Демо-вуз ${index + 1}`, programs, students: [120, 90, 60, 50, 40][index],
    })),
  };
}
