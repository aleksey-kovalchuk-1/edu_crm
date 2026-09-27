import { useSession } from "../../app/AuthGate";
import { ROLES } from "../../lib/user";
import { SenderQueuePanel } from "./SenderQueuePanel";
import { SettingsPlaceholderPage } from "./SettingsPlaceholderPage";

export function SettingsOrganizationPage() {
  const { user } = useSession();
  const manager = user.roles.includes(ROLES.supervisor) || user.roles.includes(ROLES.admin);
  return (
    <>
      <SettingsPlaceholderPage heading="Организация" subtitle="Реквизиты и контактные данные организации." />
      {manager && <SenderQueuePanel />}
    </>
  );
}
