import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import Dashboard from "./components/Dashboard";
import ModelDetail from "./components/ModelDetail";
import Compare from "./components/Compare";
import { useTheme } from "./context/ThemeContext";

export default function App() {
  const { dark, toggleTheme } = useTheme();

  return (
    <div className="flex min-h-screen flex-col bg-page text-ink">
      <header className="sticky top-0 z-40 border-b border-line bg-surface/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-6">
            <span className="text-sm font-semibold text-ink">ClawBench · 评测报告</span>
            <nav className="flex items-center gap-1 text-sm">
              <NavLink
                to="/"
                end
                className={({ isActive }) =>
                  `rounded-md px-2.5 py-1 transition-colors ${
                    isActive ? "bg-series-1/15 font-medium text-series-1" : "text-ink-2 hover:text-ink"
                  }`
                }
              >
                仪表盘
              </NavLink>
              <NavLink
                to="/compare"
                className={({ isActive }) =>
                  `rounded-md px-2.5 py-1 transition-colors ${
                    isActive ? "bg-series-1/15 font-medium text-series-1" : "text-ink-2 hover:text-ink"
                  }`
                }
              >
                模型对比
              </NavLink>
            </nav>
          </div>
          <button
            type="button"
            onClick={toggleTheme}
            className="flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-xs text-ink-2 transition-colors hover:text-ink"
            title={dark ? "切换到浅色" : "切换到深色"}
          >
            {dark ? "☀ 浅色" : "☾ 深色"}
          </button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-5">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/model/:modelId" element={<ModelDetail />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <footer className="border-t border-line py-4 text-center text-xs text-ink-3">
        ClawBench 评测报告 · 数据来源 FastAPI :4999
      </footer>
    </div>
  );
}
