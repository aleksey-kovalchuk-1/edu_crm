import { BrowserRouter, Route, Routes } from "react-router";
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
import { AppProviders } from "./AppProviders";
import { AuthGate } from "./AuthGate";
import { Layout } from "./Layout";

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
