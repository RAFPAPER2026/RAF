import {
  ClipboardCheck,
  Database,
  FileText,
  ListChecks,
  PenSquare,
  Star,
  TrendingUp,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

const NAV = [
  { to: "/list", label: "量规列表", icon: ListChecks },
  { to: "/builder", label: "量规构建", icon: PenSquare },
  { to: "/scorer", label: "评分", icon: ClipboardCheck },
  { to: "/review", label: "审核", icon: Star },
  { to: "/prompts", label: "Prompt 版本", icon: FileText },
  { to: "/optimize", label: "优化实验", icon: TrendingUp },
  { to: "/queries", label: "Query 管理", icon: Database },
];

export default function App() {
  return (
    <div className="flex min-h-screen bg-gray-50">
      <aside className="w-56 shrink-0 border-r border-gray-200 bg-white flex flex-col">
        <div className="px-4 py-5 border-b border-gray-100">
          <h1 className="text-lg font-bold text-gray-800">RAF</h1>
          <p className="text-xs text-gray-400 mt-0.5">AI Agent 评估量规平台</p>
        </div>
        <nav className="flex-1 py-3 space-y-1">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-4 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-blue-50 text-blue-700 font-medium border-r-2 border-blue-600"
                    : "text-gray-600 hover:bg-gray-50"
                }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-3 border-t border-gray-100 text-[11px] text-gray-300">
          rubr v1 · PROMPT-R / RIFT
        </div>
      </aside>
      <main className="flex-1 overflow-auto p-6 min-w-0">
        <Outlet />
      </main>
    </div>
  );
}
