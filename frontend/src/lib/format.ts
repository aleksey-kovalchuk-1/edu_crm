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

/** Date-only ISO string → "15.01.2027". */
export const formatFullDate = (s: string) =>
  new Date(s + "T12:00:00").toLocaleDateString("ru-RU");

/**
 * Default licence validity: signing date + 1 year (29 Feb → 28 Feb), as the
 * server computes it. Returns "" for an invalid date.
 */
export function addOneYear(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!match) return "";
  const year = Number(match[1]) + 1;
  const month = match[2];
  let day = match[3];
  if (month === "02" && day === "29") day = "28";
  return `${String(year).padStart(4, "0")}-${month}-${day}`;
}

/** The URL when it is an absolute http(s) address, otherwise null (never a javascript: link). */
export function safeWebsiteUrl(value: string): string | null {
  const text = value.trim();
  if (!text) return null;
  try {
    const url = new URL(/^[a-z][a-z\d+.-]*:/i.test(text) ? text : `https://${text}`);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}
