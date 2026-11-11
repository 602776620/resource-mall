/**
 * 分类标签（04 §4 固定字典）。展示层用静态映射；筛选栏从 /categories 拉取以保证一致。
 * key 与后端 CATEGORIES 对齐（03 §1）。
 */
export const CATEGORY_LABELS: Record<string, string> = {
  tutorial: "教程",
  template: "模板",
  material: "素材",
  ai_asset: "AI 资源",
  other: "其他",
};

export function categoryLabel(key: string): string {
  return CATEGORY_LABELS[key] ?? key;
}
