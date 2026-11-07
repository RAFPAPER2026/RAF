import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import App from "./App";
import "./index.css";
import BuilderPage from "./pages/BuilderPage";
import OptimizePage from "./pages/OptimizePage";
import PromptsPage from "./pages/PromptsPage";
import QueriesPage from "./pages/QueriesPage";
import ReviewPage from "./pages/ReviewPage";
import RubricListPage from "./pages/RubricListPage";
import ScorerPage from "./pages/ScorerPage";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route index element={<Navigate to="/list" replace />} />
          <Route path="/list" element={<RubricListPage />} />
          <Route path="/builder" element={<BuilderPage />} />
          <Route path="/builder/:id" element={<BuilderPage />} />
          <Route path="/scorer" element={<ScorerPage />} />
          <Route path="/scorer/:id" element={<ScorerPage />} />
          <Route path="/review/:id" element={<ReviewPage />} />
          {/* /review 缺 id（手输/刷新丢参）与任意未匹配路径 → 回列表，避免空白页 */}
          <Route path="/review" element={<Navigate to="/list" replace />} />
          <Route path="*" element={<Navigate to="/list" replace />} />
          <Route path="/prompts" element={<PromptsPage />} />
          <Route path="/optimize" element={<OptimizePage />} />
          <Route path="/queries" element={<QueriesPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
