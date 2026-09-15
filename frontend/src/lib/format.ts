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
export const formatDateTime = (s: string) =>
  new Date(/(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(s) ? s : s + "Z").toLocaleString(
    "ru-RU",
  );

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
