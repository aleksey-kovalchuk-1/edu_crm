import { BrowserRouter, Route, Routes } from "react-router";
import { AnalyticsPage } from "../pages/AnalyticsPage";
import { InteractionsPage } from "../pages/InteractionsPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { OverviewPage } from "../pages/OverviewPage";
import { TasksPage } from "../pages/TasksPage";
import { UniversitiesPage } from "../pages/UniversitiesPage";
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
