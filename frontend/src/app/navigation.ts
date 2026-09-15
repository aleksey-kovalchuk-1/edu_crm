import {
  BookMarked,
  Building2,
  ChartNoAxesCombined,
  Columns3,
  FileText,
  LayoutDashboard,
  ListChecks,
  type LucideIcon,
} from "lucide-react";

export const paths = {
  overview: "/",
  universities: "/universities",
  contracts: "/contracts",
  interactions: "/interactions",
  tasks: "/tasks",
  analytics: "/analytics",
  catalogs: "/catalogs",
} as const;

export const universityPath = (id: number) => `${paths.universities}/${id}`;

export type CreateKind = "university" | "launch" | "contract";

export interface PageMeta {
  path: string;
  name: string;
  icon: LucideIcon;
  heading: string;
  subtitle: string;
  /** What the page heading button creates; null when the page has its own actions. */
  create: CreateKind | null;
}

export const pages: PageMeta[] = [
  {
    path: paths.overview,
    name: "Обзор",
    icon: LayoutDashboard,
    heading: "Всё важное — в одном месте",
    subtitle: "Контролируйте взаимодействия и помогайте программам расти.",
    create: "launch",
  },
  {
    path: paths.universities,
    name: "Учебные заведения",
    icon: Building2,
    heading: "Учебные заведения",
    subtitle: "Единая база партнёров, контактов и образовательных программ.",
    create: "university",
  },
  {
    path: paths.contracts,
    name: "Договоры",
    icon: FileText,
    heading: "Договоры",
    subtitle: "Договоры и лицензии ИТ-продуктов, сроки действия и передача.",
    create: "contract",
  },
  {
    path: paths.interactions,
    name: "Взаимодействия",
    icon: Columns3,
    heading: "Взаимодействия",
    subtitle:
      "Полный цикл сотрудничества — от первого контакта до сопровождения.",
    create: "launch",
  },
  {
    path: paths.tasks,
    name: "Задачи",
    icon: ListChecks,
    heading: "Задачи",
    subtitle: "Ближайшие действия, сроки и ответственные.",
    create: "launch",
  },
  {
    path: paths.analytics,
    name: "Аналитика",
    icon: ChartNoAxesCombined,
    heading: "Аналитика",
    subtitle: "Динамика спроса на обучение и результаты предыдущих лет.",
    create: "launch",
  },
  {
    path: paths.catalogs,
    name: "Справочники",
    icon: BookMarked,
    heading: "Справочники",
    subtitle: "ИТ-направления и ИТ-продукты, используемые в договорах.",
    create: null,
  },
];

export const NOT_FOUND_TITLE = "Страница не найдена";

const normalize = (pathname: string) => pathname.replace(/\/+$/, "") || "/";

/** The page for a path, including its nested routes (e.g. /universities/5). */
export function findPage(pathname: string): PageMeta | undefined {
  const normalized = normalize(pathname);
  return (
    pages.find((p) => p.path === normalized) ??
    pages.find((p) => p.path !== "/" && normalized.startsWith(`${p.path}/`))
  );
}

/** True on the page itself, false on its nested routes. */
export const isPageRoot = (page: PageMeta, pathname: string) =>
  page.path === normalize(pathname);
