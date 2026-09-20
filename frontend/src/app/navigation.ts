import {
  BookMarked,
  Building2,
  ChartNoAxesCombined,
  Columns3,
  FileText,
  LayoutDashboard,
  FileUp,
  ListChecks,
  ListTree,
  UserRound,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { ROLES } from "../lib/user";

export const paths = {
  overview: "/",
  universities: "/universities",
  contracts: "/contracts",
  interactions: "/interactions",
  tasks: "/tasks",
  taskTemplates: "/tasks/templates",
  analytics: "/analytics",
  catalogs: "/catalogs",
  imports: "/imports",
  workflows: "/workflows",
  statusBoard: "/interactions/board",
  profile: "/profile",
} as const;

export const universityPath = (id: number) => `${paths.universities}/${id}`;
/** Interaction detail with the status timeline (nested under «Взаимодействия»). */
export const launchPath = (id: number) => `${paths.interactions}/${id}`;
export const taskPath = (id: number) => `${paths.tasks}/${id}`;

export type CreateKind = "university" | "launch" | "contract";

export interface PageMeta {
  path: string;
  name: string;
  icon: LucideIcon;
  heading: string;
  subtitle: string;
  /** What the page heading button creates; null when the page has its own actions. */
  create: CreateKind | null;
  /** Roles that see the page in the sidebar; absent — every CRM role. */
  roles?: string[];
  /** Reachable by path (e.g. from the profile link) but left out of the sidebar nav list. */
  hidden?: boolean;
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
    // The workspace has its own «Создать задачу» action (TasksPage), not the shared header button.
    create: null,
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
  {
    path: paths.imports,
    name: "Загрузка справочников",
    icon: FileUp,
    heading: "Загрузка справочников",
    subtitle: "Обновление договоров, вузов и ИТ-продуктов из файлов xls и xlsx.",
    create: null,
    roles: [ROLES.supervisor, ROLES.admin],
  },
  {
    path: paths.workflows,
    name: "Процессы",
    icon: Workflow,
    heading: "Процессы",
    subtitle: "Шаблоны взаимодействия: статусы, их порядок и финальные этапы.",
    create: null,
    roles: [ROLES.supervisor, ROLES.admin],
  },
  {
    path: paths.taskTemplates,
    name: "Шаблоны планов задач",
    icon: ListTree,
    heading: "Шаблоны планов задач",
    subtitle: "Повторно используемые последовательности задач для запуска сотрудничества с вузом.",
    create: null,
    hidden: true,
  },
  {
    path: paths.profile,
    name: "Профиль",
    icon: UserRound,
    heading: "Профиль",
    subtitle: "Данные вашей учётной записи и подтверждение телефона.",
    create: null,
    hidden: true,
  },
];

/** Pages shown in the sidebar for a user's roles (the server still enforces access). */
export const visiblePages = (roles: string[]) =>
  pages.filter(
    (p) => !p.hidden && (!p.roles || p.roles.some((r) => roles.includes(r))),
  );

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
