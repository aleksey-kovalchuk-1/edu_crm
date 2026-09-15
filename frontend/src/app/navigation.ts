import {
  Building2,
  ChartNoAxesCombined,
  Columns3,
  LayoutDashboard,
  ListChecks,
  type LucideIcon,
} from "lucide-react";

export const paths = {
  overview: "/",
  universities: "/universities",
  interactions: "/interactions",
  tasks: "/tasks",
  analytics: "/analytics",
} as const;

export interface PageMeta {
  path: string;
  name: string;
  icon: LucideIcon;
  heading: string;
  subtitle: string;
  create: "university" | "launch";
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
];

export const NOT_FOUND_TITLE = "Страница не найдена";

export function findPage(pathname: string): PageMeta | undefined {
  const normalized = pathname.replace(/\/+$/, "") || "/";
  return pages.find((p) => p.path === normalized);
}
