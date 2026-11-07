import type { ReactNode } from 'react'

interface Props {
  title: ReactNode
  onClose?: () => void
  children: ReactNode
  /** 弹窗宽度档位 */
  size?: 'md' | 'lg' | 'xl'
}

const SIZES: Record<NonNullable<Props['size']>, string> = {
  md: 'max-w-lg',
  lg: 'max-w-3xl',
  xl: 'max-w-6xl',
}

export default function Modal({ title, onClose, children, size = 'lg' }: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className={`flex max-h-[92vh] w-full ${SIZES[size]} flex-col rounded-xl bg-white shadow-2xl`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-5 py-3">
          <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
          {onClose && (
            <button
              onClick={onClose}
              className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              title="关闭"
            >
              ✕
            </button>
          )}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>
  )
}
