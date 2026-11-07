import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { TaskScore } from "../../types";
import {
  MANUAL_SCORED,
  MANUAL_UNSCORED,
  extractDimensionOptions,
} from "../../utils/filterUtils";

/** 筛选状态：维度 → 选中值集合（空/未定义 = 不筛选） */
export type FilterState = Record<string, string[] | undefined>;

export const EMPTY_FILTERS: FilterState = {};

interface FilterGroupDef {
  key: string;
  label: string;
  options: Array<{ value: string; label: string }>;
}

interface CrossFilterPanelProps {
  tasks: TaskScore[];
  filters: FilterState;
  onChange: (next: FilterState) => void;
}

const DIMENSION_GROUPS = [
  "primary_scenario",
  "secondary_scenario",
  "ability_category",
  "difficulty",
  "complexity",
] as const;

const DIMENSION_LABELS: Record<string, string> = {
  primary_scenario: "主场景",
  secondary_scenario: "次场景",
  ability_category: "能力",
  difficulty: "难度",
  complexity: "复杂度",
};

/** 可折叠交叉筛选面板：维度间 AND、维度内 OR */
export function CrossFilterPanel({ tasks, filters, onChange }: CrossFilterPanelProps) {
  const [open, setOpen] = useState(false);

  const groups = useMemo<FilterGroupDef[]>(() => {
    const defs: FilterGroupDef[] = [];
    for (const dim of DIMENSION_GROUPS) {
      const opts = extractDimensionOptions(tasks, dim);
      if (opts.length > 0) {
        defs.push({
          key: dim,
          label: DIMENSION_LABELS[dim] ?? dim,
          options: opts.map((v) => ({ value: v, label: v })),
        });
      }
    }
    defs.push({
      key: "manual_score_status",
      label: "人工评分状态",
      options: [
        { value: MANUAL_SCORED, label: "已评分" },
        { value: MANUAL_UNSCORED, label: "未评分" },
      ],
    });
    return defs;
  }, [tasks]);

  const activeCount = useMemo(
    () => Object.values(filters).reduce((n, v) => n + (v?.length ?? 0), 0),
    [filters],
  );

  const toggleValue = (dim: string, value: string) => {
    const current = filters[dim] ?? [];
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    onChange({ ...filters, [dim]: next.length > 0 ? next : undefined });
  };

  const clearAll = () => onChange(EMPTY_FILTERS);

  return (
    <div className="rounded-xl border border-line bg-surface shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 text-sm font-medium text-ink">
          交叉筛选
          {activeCount > 0 ? (
            <span className="rounded-full bg-series-1/15 px-2 py-0.5 text-xs font-semibold text-series-1">
              {activeCount}
            </span>
          ) : null}
        </span>
        <span className="flex items-center gap-2">
          {activeCount > 0 ? (
            <span
              role="button"
              tabIndex={0}
              className="text-xs text-ink-3 hover:text-critical"
              onClick={(e) => {
                e.stopPropagation();
                clearAll();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.stopPropagation();
                  clearAll();
                }
              }}
            >
              清除全部
            </span>
          ) : null}
          <span
            className={`inline-block h-2 w-2 border-y-4 border-x-4 border-y-transparent border-l-ink-2 transition-transform ${
              open ? "rotate-90" : ""
            }`}
            style={{ borderLeftColor: "var(--ink-2)" }}
            aria-hidden
          />
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="panel"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="grid grid-cols-1 gap-x-6 gap-y-4 border-t border-line px-4 py-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {groups.map((g) => {
                const selected = filters[g.key] ?? [];
                return (
                  <div key={g.key}>
                    <div className="mb-1.5 flex items-center justify-between">
                      <span className="text-xs font-medium text-ink-2">{g.label}</span>
                      {selected.length > 0 ? (
                        <span className="text-[11px] text-ink-3">{selected.length} 项</span>
                      ) : null}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {g.options.map((opt) => {
                        const active = selected.includes(opt.value);
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            onClick={() => toggleValue(g.key, opt.value)}
                            className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                              active
                                ? "border-series-1 bg-series-1/15 font-medium text-series-1"
                                : "border-line bg-surface-2 text-ink-2 hover:border-ink-3"
                            }`}
                            aria-pressed={active}
                          >
                            {opt.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
