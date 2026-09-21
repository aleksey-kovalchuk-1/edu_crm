import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { AnalyticsPage } from "../pages/AnalyticsPage";
import { CatalogsPage } from "../pages/CatalogsPage";
import { ContractsPage } from "../pages/ContractsPage";
import { ImportsPage } from "../pages/ImportsPage";
import { InteractionsPage } from "../pages/InteractionsPage";
import { LaunchPage } from "../pages/LaunchPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { OverviewPage } from "../pages/OverviewPage";
import { ProfilePage } from "../pages/ProfilePage";
import { StatusBoardPage } from "../pages/StatusBoardPage";
import { TaskDetailPage } from "../pages/TaskDetailPage";
import { TaskTemplatesPage } from "../pages/TaskTemplatesPage";
import { TasksPage } from "../pages/TasksPage";
import { UniversitiesPage } from "../pages/UniversitiesPage";
import { UniversityPage } from "../pages/UniversityPage";
import { WorkflowsPage } from "../pages/WorkflowsPage";
import { SettingsBackupsPage } from "../pages/settings/SettingsBackupsPage";
import { SettingsNotificationsPage } from "../pages/settings/SettingsNotificationsPage";
import { SettingsOrganizationPage } from "../pages/settings/SettingsOrganizationPage";
import { SettingsPersonalDataPage } from "../pages/settings/SettingsPersonalDataPage";
import { SettingsProfilePage } from "../pages/settings/SettingsProfilePage";
import { SettingsSecurityPage } from "../pages/settings/SettingsSecurityPage";
import { SettingsUsersPage } from "../pages/settings/SettingsUsersPage";
import { AppProviders } from "./AppProviders";
import { AuthGate } from "./AuthGate";
import { Layout } from "./Layout";
import { paths } from "./navigation";

export function AppRoutes() {
  return (
    <AuthGate>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<OverviewPage />} />
          <Route path="universities" element={<UniversitiesPage />} />
          <Route path="universities/:id" element={<UniversityPage />} />
          <Route path="contracts" element={<ContractsPage />} />
          <Route path="catalogs" element={<CatalogsPage />} />
          <Route path="imports" element={<ImportsPage />} />
          <Route path="interactions" element={<InteractionsPage />} />
          <Route path="interactions/board" element={<StatusBoardPage />} />
          <Route path="interactions/:id" element={<LaunchPage />} />
          <Route path="workflows" element={<WorkflowsPage />} />
          <Route path="tasks" element={<TasksPage />} />
          <Route path="tasks/templates" element={<TaskTemplatesPage />} />
          <Route path="tasks/:id" element={<TaskDetailPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route
            path="settings"
            element={<Navigate to={paths.settingsProfile} replace />}
          />
          <Route path="settings/profile" element={<SettingsProfilePage />} />
          <Route path="settings/organization" element={<SettingsOrganizationPage />} />
          <Route path="settings/notifications" element={<SettingsNotificationsPage />} />
          <Route path="settings/security" element={<SettingsSecurityPage />} />
          <Route path="settings/users" element={<SettingsUsersPage />} />
          <Route path="settings/personal-data" element={<SettingsPersonalDataPage />} />
          <Route path="settings/backups" element={<SettingsBackupsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </AuthGate>
  );
}

export default function App() {
  return (
    <AppProviders>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AppProviders>
  );
}
