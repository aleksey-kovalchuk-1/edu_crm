/** Board columns: groups of workflow stages. */
export const stageGroups = [
  "Первый контакт",
  "Документы",
  "Внедрение",
  "Обучение",
  "Сопровождение",
];

/** Index of the board column a stage belongs to. */
export const stageGroup = (stage: number) =>
  stage < 3 ? 0 : stage < 6 ? 1 : stage < 8 ? 2 : stage < 11 ? 3 : 4;

export const formatNumber = (n: number) =>
  new Intl.NumberFormat("ru-RU").format(n);

/** Date-only ISO string (YYYY-MM-DD) → "5 мар." */
export const formatDate = (s: string) =>
  new Date(s + "T12:00:00").toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
  });

/** Server timestamp; values without a zone are treated as UTC. */
export const parseServerDate = (s: string) =>
  new Date(/(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(s) ? s : s + "Z");

export const formatDateTime = (s: string) =>
  parseServerDate(s).toLocaleString("ru-RU");

/** «только что», «5 мин назад», «3 ч назад»; older than a day — date and time. */
export function formatRelativeTime(s: string, now: number): string {
  const date = parseServerDate(s);
  if (Number.isNaN(date.getTime())) return "";
  const minutes = Math.floor((now - date.getTime()) / 60_000);
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  const sameYear = date.getFullYear() === new Date(now).getFullYear();
  return date.toLocaleString("ru-RU", {
    day: "numeric",
    month: "short",
    ...(sameYear ? {} : { year: "numeric" }),
    hour: "2-digit",
    minute: "2-digit",
  });
}

export const initials = (s: string) =>
  s
    .split(" ")
    .slice(0, 2)
    .map((x) => x[0])
    .join("");

export const launchCode = (id: number) => `ВЗ-${String(id).padStart(4, "0")}`;

/** CSV cell with quoting and protection against spreadsheet formula injection. */
export const csvCell = (v: string | number) =>
  '"' +
  String(v)
    .replace(/^[=+@-]/, "'$&")
    .replaceAll('"', '""') +
  '"';

export const toCsv = (rows: (string | number)[][]) =>
  "﻿" + rows.map((r) => r.map(csvCell).join(";")).join("\n");

export const matches = (haystack: string, query: string) =>
  haystack.toLowerCase().includes(query.toLowerCase());
