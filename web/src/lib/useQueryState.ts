/**
 * 列表筛选态 → URL query（02 §3「partial：分页/筛选变更保留 query 于 URL」）。
 * 只管理给定 key 集合；空值（""/undefined）从 URL 移除，保留其它参数。
 */
import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

export interface QueryPatch {
  category?: string;
  keyword?: string;
  sort?: string;
  price_min?: string;
  price_max?: string;
  page?: string;
}

export function useQueryState() {
  const [params, setParams] = useSearchParams();

  const get = useCallback(
    (k: keyof QueryPatch) => params.get(k) ?? "",
    [params],
  );

  /** 更新若干筛选 key；其它已有参数不动。page 缺省重置为 1。 */
  const patch = useCallback(
    (p: QueryPatch) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          (Object.keys(p) as (keyof QueryPatch)[]).forEach((k) => {
            const v = p[k];
            if (v === undefined) return;
            if (v === "" || v === null) next.delete(k);
            else next.set(k, v);
          });
          // 变更筛选但没显式带 page → 回到第 1 页
          if (p.page === undefined) next.delete("page");
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  /** 仅改页码，保留筛选。 */
  const setPage = useCallback(
    (page: number) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (page <= 1) next.delete("page");
          else next.set("page", String(page));
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  return { get, patch, setPage };
}
