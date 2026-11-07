// 环形分数图
interface ScoreRingProps {
  value: number; // 0-1
  size?: number;
  label?: string;
  sublabel?: string;
}

export default function ScoreRing({ value, size = 120, label, sublabel }: ScoreRingProps) {
  const stroke = 10;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(1, value));
  const color = clamped >= 0.8 ? "#16a34a" : clamped >= 0.5 ? "#ca8a04" : "#dc2626";

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e5e7eb" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeDasharray={`${c * clamped} ${c}`}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text
          x="50%"
          y="50%"
          dominantBaseline="central"
          textAnchor="middle"
          fontSize={size / 5}
          fontWeight={700}
          fill={color}
        >
          {Math.round(clamped * 100)}%
        </text>
      </svg>
      {label && <div className="text-sm font-medium text-gray-700">{label}</div>}
      {sublabel && <div className="text-xs text-gray-400">{sublabel}</div>}
    </div>
  );
}
