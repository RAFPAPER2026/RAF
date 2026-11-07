// 优化流程步骤条
interface StepIndicatorProps {
  steps: string[];
  current: number; // 当前步骤（0-based）
}

export default function StepIndicator({ steps, current }: StepIndicatorProps) {
  return (
    <div className="flex items-center flex-wrap gap-y-2">
      {steps.map((s, i) => (
        <div key={s} className="flex items-center">
          <div className="flex items-center gap-1.5">
            <span
              className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium shrink-0 ${
                i < current
                  ? "bg-green-500 text-white"
                  : i === current
                    ? "bg-blue-600 text-white"
                    : "bg-gray-200 text-gray-500"
              }`}
            >
              {i < current ? "✓" : i + 1}
            </span>
            <span
              className={`text-xs whitespace-nowrap ${
                i === current
                  ? "font-semibold text-blue-700"
                  : i < current
                    ? "text-green-600"
                    : "text-gray-400"
              }`}
            >
              {s}
            </span>
          </div>
          {i < steps.length - 1 && (
            <div className={`w-6 h-px mx-1.5 ${i < current ? "bg-green-400" : "bg-gray-200"}`} />
          )}
        </div>
      ))}
    </div>
  );
}
