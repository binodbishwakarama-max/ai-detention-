import { Routes, Route, Navigate } from "react-router-dom";
import { DashboardLayout } from "./components/layout/DashboardLayout";
import { Dashboard } from "./pages/Dashboard/Dashboard";
import { EvaluationsList } from "./pages/Evaluations/EvaluationsList";
import { EvaluationDetail } from "./pages/Evaluations/EvaluationDetail";
import { SubmissionsList } from "./pages/Submissions/SubmissionsList";
import { SubmissionDetail } from "./pages/Submissions/SubmissionDetail";
import { SubmissionCreate } from "./pages/Submissions/SubmissionCreate";
import { DatasetsList } from "./pages/Datasets/DatasetsList";
import { MetricsList } from "./pages/Metrics/MetricsList";
import { SettingsPage } from "./pages/Settings/SettingsPage";

function App() {
  return (
    <Routes>
      <Route element={<DashboardLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="submissions" element={<SubmissionsList />} />
        <Route path="submissions/new" element={<SubmissionCreate />} />
        <Route path="submissions/:submissionId" element={<SubmissionDetail />} />
        <Route path="evaluations" element={<EvaluationsList />} />
        <Route path="evaluations/:runId" element={<EvaluationDetail />} />
        <Route path="datasets" element={<DatasetsList />} />
        <Route path="metrics" element={<MetricsList />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
