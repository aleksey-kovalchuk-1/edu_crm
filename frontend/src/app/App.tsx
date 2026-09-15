import { BrowserRouter, Route, Routes } from "react-router";
import { AnalyticsPage } from "../pages/AnalyticsPage";
import { CatalogsPage } from "../pages/CatalogsPage";
import { ContractsPage } from "../pages/ContractsPage";
import { InteractionsPage } from "../pages/InteractionsPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { OverviewPage } from "../pages/OverviewPage";
import { TasksPage } from "../pages/TasksPage";
import { UniversitiesPage } from "../pages/UniversitiesPage";
import { UniversityPage } from "../pages/UniversityPage";
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
          <Route path="interactions" element={<InteractionsPage />} />
          <Route path="tasks" element={<TasksPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
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
