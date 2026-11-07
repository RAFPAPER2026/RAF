// 星级评分（1-5）
import { Star } from "lucide-react";

interface StarRatingProps {
  value: number;
  onChange?: (v: number) => void;
  label?: string;
}

export default function StarRating({ value, onChange, label }: StarRatingProps) {
  return (
    <div className="flex items-center gap-2">
      {label && <span className="text-sm text-gray-600">{label}</span>}
      <div className="flex items-center gap-0.5">
        {[1, 2, 3, 4, 5].map((i) => (
          <button
            key={i}
            type="button"
            disabled={!onChange}
            onClick={() => onChange?.(i)}
            className={onChange ? "cursor-pointer hover:scale-110 transition-transform" : "cursor-default"}
            title={`${i} 星`}
          >
            <Star
              size={20}
              className={i <= value ? "fill-amber-400 text-amber-400" : "text-gray-300"}
            />
          </button>
        ))}
      </div>
      <span className="text-xs text-gray-400">{value}/5</span>
    </div>
  );
}
