import { useState } from "react";
import type { ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";

interface SectionCardProps {
  title: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  collapsible?: boolean;
  defaultOpen?: boolean;
  children: ReactNode;
}

/** 区块卡：标题 + 可选右侧操作 + 可折叠内容 */
export function SectionCard({
  title,
  subtitle,
  right,
  collapsible = false,
  defaultOpen = true,
  children,
}: SectionCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const showToggle = collapsible;

  return (
    <div className="rounded-xl border border-line bg-surface shadow-sm">
      <div className="flex items-center justify-between gap-3 px-4 pt-3.5 pb-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {showToggle ? (
              <button
                type="button"
                onClick={() => setOpen((o) => !o)}
                className="text-sm font-medium text-ink hover:text-ink-2 transition-colors"
                aria-expanded={open}
              >
                <span
                  className="mr-1 inline-block w-0 h-0 border-y-4 border-l-4 border-y-transparent transition-transform"
                  style={{
                    borderLeftColor: "currentColor",
                    transform: open ? "rotate(90deg)" : "none",
                  }}
                />
                {title}
              </button>
            ) : (
              <h3 className="text-sm font-medium text-ink">{title}</h3>
            )}
          </div>
          {subtitle ? <div className="mt-0.5 text-xs text-ink-3">{subtitle}</div> : null}
        </div>
        {right ? <div className="shrink-0">{right}</div> : null}
      </div>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4">{children}</div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
