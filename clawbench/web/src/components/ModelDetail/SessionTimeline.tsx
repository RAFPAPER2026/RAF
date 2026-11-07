import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { SessionsData } from "../../api/client";
import { fmtDuration } from "../../utils/format";

interface SessionTimelineProps {
  data: SessionsData | null;
  loading: boolean;
  taskName: string;
}

/** 会话轨迹侧栏：container 名 + 各会话事件关键信息（可展开原始 JSON）。
 *  sessions.json 现为 openclaw **完整原始记录**（`type=="message"` + `message.role`），
 *  与 SDK 风格事件形状并存，展示层对两者均兼容。 */
export function SessionTimeline({ data, loading, taskName }: SessionTimelineProps) {
  return (
    <div className="rounded-xl border border-line bg-surface shadow-sm">
      <div className="border-b border-line px-4 py-2.5 text-sm font-medium text-ink">
        会话轨迹
        <span className="ml-2 text-xs font-normal text-ink-3">{taskName}</span>
      </div>
      <div className="max-h-[520px] overflow-y-auto p-3">
        {loading ? (
          <div className="py-6 text-center text-xs text-ink-3">加载中…</div>
        ) : !data ? (
          <div className="py-6 text-center text-xs text-ink-3">无会话数据</div>
        ) : (
          <div className="space-y-2">
            {data.container ? (
              <div className="text-xs text-ink-2">
                <span className="text-ink-3">容器：</span>
                <span className="code-block">{data.container}</span>
              </div>
            ) : null}
            {data.sessions.length === 0 ? (
              <div className="py-4 text-center text-xs text-ink-3">空会话</div>
            ) : null}
            {data.sessions.map((s, i) => (
              <SessionItem key={i} session={s} index={i} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** 事件类型/角色标签：openclaw 原始记录取 `message.role`，SDK 事件取 `type`。 */
function recordType(s: Record<string, unknown>): string | null {
  if (typeof s["type"] === "string") {
    if (s["type"] === "message") {
      const msg = s["message"];
      if (msg && typeof msg === "object") {
        const role = (msg as Record<string, unknown>)["role"];
        if (typeof role === "string") return role === "toolResult" ? "tool_result" : role;
      }
    }
    return s["type"] as string;
  }
  if (typeof s["role"] === "string") return s["role"] as string;
  return null;
}

function recordContent(s: Record<string, unknown>): unknown {
  const msg = s["message"];
  if (msg && typeof msg === "object") {
    const mc = (msg as Record<string, unknown>)["content"];
    if (Array.isArray(mc)) return mc;
  }
  return s["content"];
}

function recordSummary(s: Record<string, unknown>): string {
  const content = recordContent(s);
  if (typeof content === "string") return content.slice(0, 80);
  if (Array.isArray(content)) {
    const parts: string[] = [];
    for (const b of content) {
      if (!b || typeof b !== "object") continue;
      const block = b as Record<string, unknown>;
      const t = block["type"];
      if (t === "text" && typeof block["text"] === "string" && block["text"].trim()) {
        parts.push(block["text"] as string);
      } else if (t === "toolCall" || t === "tool_use") {
        parts.push(`🛠 ${String(block["name"] ?? "tool")}`);
      } else if (t === "tool_result") {
        const inner = block["content"];
        parts.push(typeof inner === "string" ? `↩ ${inner.slice(0, 40)}` : "↩ tool_result");
      }
    }
    const joined = parts.join(" ");
    return joined.slice(0, 80);
  }
  return "";
}

function SessionItem({ session, index }: { session: unknown; index: number }) {
  const [open, setOpen] = useState(false);
  const s = (session ?? {}) as Record<string, unknown>;
  const score = typeof s["score"] === "number" ? s["score"] : null;
  const status = typeof s["status"] === "string" ? s["status"] : null;
  const duration = typeof s["duration"] === "number" ? s["duration"] : null;
  const passed = score !== null ? score >= 0.75 : null;
  const type = recordType(s);
  const title = type ?? `Session ${index + 1}`;
  const summary = recordSummary(s);
  const ts =
    typeof s["timestamp"] === "string"
      ? s["timestamp"]
      : typeof s["time"] === "string"
        ? s["time"]
        : null;
  const msg = s["message"] && typeof s["message"] === "object" ? (s["message"] as Record<string, unknown>) : null;
  const isError = Boolean((msg && msg["isError"]) ?? s["is_error"]);
  const dotClass =
    passed === null ? (isError ? "bg-critical" : "bg-ink-3") : passed ? "bg-good" : "bg-critical";

  return (
    <div className="rounded-lg border border-line bg-surface-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-2.5 py-2 text-left"
      >
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotClass}`} aria-hidden />
        {type ? (
          <span className="rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[10px] text-ink-2">
            {index + 1}
          </span>
        ) : null}
        <span className="text-xs font-medium text-ink">{title}</span>
        {ts ? <span className="shrink-0 font-mono text-[10px] text-ink-3">{ts}</span> : null}
        {status ? <span className="text-[11px] text-ink-3">{status}</span> : null}
        {score !== null ? (
          <span className="tnum text-[11px] text-ink-2">{(score * 100).toFixed(1)}%</span>
        ) : null}
        {duration !== null ? (
          <span className="tnum ml-auto text-[11px] text-ink-3">{fmtDuration(duration)}</span>
        ) : null}
      </button>
      {summary ? (
        <p className="truncate px-2.5 pb-1.5 text-[11px] text-ink-2" title={summary}>
          {summary}
        </p>
      ) : null}
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <pre className="code-block max-h-56 overflow-y-auto border-t border-line px-2.5 py-2 text-ink-2">
              {JSON.stringify(s, null, 2)}
            </pre>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
