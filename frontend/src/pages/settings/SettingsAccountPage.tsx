import { LogOut } from "lucide-react";
import { useSession, useSignOut } from "../../app/AuthGate";
import { AdminUsersPanel } from "../../components/AdminUsersPanel";
import { ErrorAlert } from "../../components/QueryState";
import { ROLES } from "../../lib/user";

export function SettingsAccountPage() {
  const { user } = useSession();
  const logout = useSignOut();
  const isSuperadmin = user.roles.includes(ROLES.superadmin);

  return (
    <>
      <section className="panel" aria-labelledby="account-title">
        <div className="section-head">
          <div>
            <h2 id="account-title">Аккаунт</h2>
            <p>
              Вы вошли как <strong>{user.full_name || user.email}</strong> ({user.email}).
            </p>
          </div>
        </div>
        {logout.error && <ErrorAlert error={logout.error} />}
        <div className="wizard-actions">
          <button
            type="button"
            className="secondary danger"
            disabled={logout.isPending || logout.isSuccess}
            onClick={() => logout.mutate()}
          >
            <LogOut size={16} />
            {logout.isPending ? "Выходим…" : "Выйти из аккаунта"}
          </button>
        </div>
      </section>
      {isSuperadmin && <AdminUsersPanel />}
    </>
  );
}
