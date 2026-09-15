export const ROLES = {
  user: "crm-user",
  supervisor: "crm-supervisor",
  admin: "crm-admin",
} as const;

/** Highest role first. */
const ROLE_LABELS: [string, string][] = [
  [ROLES.admin, "Администратор"],
  [ROLES.supervisor, "Руководитель"],
  [ROLES.user, "Менеджер"],
];

/** Russian label of the highest CRM role, or null when the user has none. */
export const roleLabel = (roles: string[]): string | null =>
  ROLE_LABELS.find(([role]) => roles.includes(role))?.[1] ?? null;

export const hasCrmAccess = (roles: string[]) => roleLabel(roles) !== null;

/** Creating and editing catalog records (universities) — supervisors and admins. */
export const canEditCatalog = (roles: string[]) =>
  roles.includes(ROLES.supervisor) || roles.includes(ROLES.admin);

/** Uploading catalogs from xls/xlsx files (T-033) — supervisors and admins. */
export const canImportCatalogs = (roles: string[]) =>
  roles.includes(ROLES.supervisor) || roles.includes(ROLES.admin);

/** Supervisors and admins see everyone's actions; a crm-user sees only their own. */
export const seesAllActions = (roles: string[]) =>
  roles.includes(ROLES.supervisor) || roles.includes(ROLES.admin);

export const userInitials = (user: { full_name: string; email: string }) =>
  (
    user.full_name
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0])
      .join("") || user.email.slice(0, 1)
  ).toUpperCase();
