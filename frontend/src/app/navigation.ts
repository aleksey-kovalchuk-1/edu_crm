import {
  Bell,
  BookMarked,
  Building2,
  ChartNoAxesCombined,
  Columns3,
  DatabaseBackup,
  FileLock2,
  FileText,
  LayoutDashboard,
  FileUp,
  ListChecks,
  ListTree,
  LogOut,
  ShieldCheck,
  UserRound,
  Users,
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
  settings: "/settings",
  settingsProfile: "/settings/profile",
  settingsOrganization: "/settings/organization",
  settingsNotifications: "/settings/notifications",
  settingsSecurity: "/settings/security",
  settingsUsers: "/settings/users",
  settingsPersonalData: "/settings/personal-data",
  settingsBackups: "/settings/backups",
  settingsAccount: "/settings/account",
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
];

/** Settings pages, reachable via the «Настройки» submenu (Task 3); never shown in the flat sidebar list. */
export const settingsPages: PageMeta[] = [
  {
    path: paths.settingsProfile,
    name: "Личный профиль",
    icon: UserRound,
    heading: "Личный профиль",
    subtitle: "Имя, контакты, язык интерфейса и часовой пояс.",
    create: null,
    hidden: true,
  },
  {
    path: paths.settingsOrganization,
    name: "Организация",
    icon: Building2,
    heading: "Организация",
    subtitle: "Реквизиты и контактные данные организации.",
    create: null,
    hidden: true,
  },
  {
    path: paths.settingsNotifications,
    name: "Уведомления",
    icon: Bell,
    heading: "Уведомления",
    subtitle: "Какие события присылают уведомления и когда.",
    create: null,
    hidden: true,
  },
  {
    path: paths.settingsSecurity,
    name: "Безопасность",
    icon: ShieldCheck,
    heading: "Безопасность",
    subtitle: "Активные сеансы и политика паролей.",
    create: null,
    hidden: true,
  },
  {
    path: paths.settingsUsers,
    name: "Пользователи и роли",
    icon: Users,
    heading: "Пользователи и роли",
    subtitle: "Учётные записи, роли и заявки на доступ.",
    create: null,
    hidden: true,
    roles: [ROLES.superadmin],
  },
  {
    path: paths.settingsPersonalData,
    name: "Персональные данные",
    icon: FileLock2,
    heading: "Персональные данные",
    subtitle: "Обработка персональных данных.",
    create: null,
    hidden: true,
  },
  {
    path: paths.settingsBackups,
    name: "Резервное копирование",
    icon: DatabaseBackup,
    heading: "Резервное копирование",
    subtitle: "Статус резервных копий базы данных и вложений.",
    create: null,
    hidden: true,
    roles: [ROLES.superadmin],
  },
  {
    path: paths.settingsAccount,
    name: "Аккаунт",
    icon: LogOut,
    heading: "Аккаунт",
    subtitle: "Выход из аккаунта и обзор пользователей CRM.",
    create: null,
    hidden: true,
  },
];

/** Pages shown in the sidebar for a user's roles (the server still enforces access). */
export const visiblePages = (roles: string[]) =>
  pages.filter(
    (p) => !p.hidden && (!p.roles || p.roles.some((r) => roles.includes(r))),
  );

/**
 * Every page findPage() can resolve to — the flat sidebar pages plus the settings submenu
 * pages, which are deliberately excluded from `pages`/`visiblePages()` (they must never
 * appear in the flat sidebar list) but still need a header/breadcrumb when routed to.
 */
const allPages: PageMeta[] = [...pages, ...settingsPages];

export const NOT_FOUND_TITLE = "Страница не найдена";

const normalize = (pathname: string) => pathname.replace(/\/+$/, "") || "/";

/** The page for a path, including its nested routes (e.g. /universities/5). */
export function findPage(pathname: string): PageMeta | undefined {
  const normalized = normalize(pathname);
  return (
    allPages.find((p) => p.path === normalized) ??
    allPages.find((p) => p.path !== "/" && normalized.startsWith(`${p.path}/`))
  );
}

/** True on the page itself, false on its nested routes. */
export const isPageRoot = (page: PageMeta, pathname: string) =>
  page.path === normalize(pathname);
