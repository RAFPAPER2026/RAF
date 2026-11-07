// 评分状态管理：逐叶子勾选 → 实时计算 completion/quality 分数
import { useCallback, useMemo, useState } from "react";
import { evaluateCompletion, scoreQuality, ScoringMode } from "../lib/scoring";
import { QueryRubric } from "../lib/types";

export function useScorerState(rubric: QueryRubric | null) {
  const [results, setResults] = useState<Record<string, boolean>>({});
  const [scoringMode, setScoringMode] = useState<ScoringMode>("paper");

  const completion = useMemo(
    () => (rubric ? evaluateCompletion(rubric.completion_rubric, results) : null),
    [rubric, results]
  );
  const quality = useMemo(
    () => (rubric ? scoreQuality(rubric.quality_rubric, results, scoringMode) : null),
    [rubric, results, scoringMode]
  );

  const toggle = useCallback((id: string) => {
    setResults((prev) => ({ ...prev, [id]: !prev[id] }));
  }, []);

  const reset = useCallback(() => setResults({}), []);

  return { results, completion, quality, toggle, reset, setResults, scoringMode, setScoringMode };
}
