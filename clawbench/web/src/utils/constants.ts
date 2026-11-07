import { SERIES_LIGHT, SERIES_DARK } from "./chartTheme";

/** 模型分类色（浅色；固定顺序，按模型出现次序分配，不随排序改变） */
export const MODEL_COLORS: string[] = SERIES_LIGHT;

/** 模型分类色（深色表面） */
export const MODEL_COLORS_DARK: string[] = SERIES_DARK;

/** 排名徽标颜色 */
export const RANK_COLORS = ["#eda100", "#9aa3a8", "#eb6834"];

/** 维度展示名 */
export const DIMENSION_LABELS: Record<string, string> = {
  primary_scenario: "主场景",
  secondary_scenario: "次场景",
  ability_category: "能力",
  difficulty: "难度",
  complexity: "复杂度",
};

/** 难度分布标签映射 */
export const DIFFICULTY_LABELS: Record<string, string> = {
  easy: "简单",
  medium: "中等",
  hard: "困难",
};

export const DIFFICULTY_ORDER = ["easy", "medium", "hard"];
