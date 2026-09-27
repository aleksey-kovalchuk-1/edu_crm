import { useSession } from "../../app/AuthGate";
import { ROLES } from "../../lib/user";
import { OrganizationCard } from "./OrganizationCard";
import { SenderQueuePanel } from "./SenderQueuePanel";

export function SettingsOrganizationPage() {
  const { user } = useSession();
  const canEdit = user.roles.includes(ROLES.admin) || user.roles.includes(ROLES.superadmin);
  const manager = user.roles.includes(ROLES.supervisor) || user.roles.includes(ROLES.admin);
  return (
    <>
      <OrganizationCard canEdit={canEdit} />
      {manager && <SenderQueuePanel />}
    </>
  );
}
