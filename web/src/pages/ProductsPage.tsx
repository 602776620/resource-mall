/**
 * 资源列表（02 §1 /products）。左侧筛选栏 + 顶部排序 + 底部分页（20/页）。
 * 筛选/分页态存 URL query（02 §3 partial，可分享/回退）。金额走 formatFen。
 */
import { useEffect, useState, type FormEvent } from "react";
import { useAsync } from "@/lib/useAsync";
import { useQueryState } from "@/lib/useQueryState";
import {
  getCategories,
  listProducts,
  type Category,
  type ListProductsParams,
} from "@/api/products";
import { ProductCard } from "@/components/ProductCard";

const SORTS = [
  { key: "new", label: "最新" },
  { key: "price_asc", label: "价格 ↑" },
  { key: "price_desc", label: "价格 ↓" },
] as const;

export function ProductsPage() {
  const q = useQueryState();
  const [cats, setCats] = useState<Category[]>([]);
  const [keywordDraft, setKeywordDraft] = useState(q.get("keyword"));
  const [minDraft, setMinDraft] = useState(q.get("price_min"));
  const [maxDraft, setMaxDraft] = useState(q.get("price_max"));

  const category = q.get("category");
  const keyword = q.get("keyword");
  const sort = (q.get("sort") || "new") as ListProductsParams["sort"];
  const priceMin = q.get("price_min");
  const priceMax = q.get("price_max");
  const page = Number(q.get("page") || 1);

  useEffect(() => {
    getCategories().then(setCats).catch(() => {});
    // 同步草稿框与 URL（外部改 URL 时）
    setKeywordDraft(keyword);
    setMinDraft(priceMin);
    setMaxDraft(priceMax);
  }, [keyword, priceMin, priceMax]);

  const params: ListProductsParams = {
    category: category || undefined,
    keyword: keyword || undefined,
    sort,
    price_min_cents: priceMin ? Number(priceMin) : undefined,
    price_max_cents: priceMax ? Number(priceMax) : undefined,
    page,
    page_size: 20,
  };

  const { data, loading, error, reload } = useAsync(() => listProducts(params), [
    JSON.stringify(params),
  ]);

  const submitKeyword = (e: FormEvent) => {
    e.preventDefault();
    q.patch({ keyword: keywordDraft.trim() });
  };
  const submitPrice = () => {
    q.patch({ price_min: minDraft.trim(), price_max: maxDraft.trim() });
  };
  const resetFilters = () => {
    setKeywordDraft("");
    setMinDraft("");
    setMaxDraft("");
    q.patch({ category: "", keyword: "", sort: "new", price_min: "", price_max: "", page: "" });
  };

  const total = data?.total ?? 0;
  const pageSize = data?.page_size ?? 20;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="products-page">
      <aside className="filter-bar">
        <h2>筛选</h2>
        <div className="filter-group">
          <h3>分类</h3>
          <button
            className={category === "" ? "chip active" : "chip"}
            onClick={() => q.patch({ category: "" })}
          >
            全部
          </button>
          {cats.map((c) => (
            <button
              key={c.key}
              className={category === c.key ? "chip active" : "chip"}
              onClick={() => q.patch({ category: c.key })}
            >
              {c.label}
            </button>
          ))}
        </div>
        <div className="filter-group">
          <h3>价格区间（元）</h3>
          <div className="price-inputs">
            <input
              type="number"
              min="0"
              placeholder="最低"
              value={minDraft}
              onChange={(e) => setMinDraft(e.target.value)}
            />
            <span className="muted">—</span>
            <input
              type="number"
              min="0"
              placeholder="最高"
              value={maxDraft}
              onChange={(e) => setMaxDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submitPrice()}
            />
          </div>
          <div className="filter-actions">
            <button className="btn" onClick={submitPrice}>
              应用价格
            </button>
            <button className="btn btn-ghost" onClick={resetFilters}>
              重置
            </button>
          </div>
        </div>
      </aside>

      <section className="products-main">
        <div className="products-toolbar">
          <form className="search-box" onSubmit={submitKeyword}>
            <input
              type="search"
              placeholder="搜索标题或标签…"
              value={keywordDraft}
              onChange={(e) => setKeywordDraft(e.target.value)}
            />
            <button className="btn" type="submit">
              搜索
            </button>
          </form>
          <div className="sort-group">
            {SORTS.map((s) => (
              <button
                key={s.key}
                className={sort === s.key ? "chip active" : "chip"}
                onClick={() => q.patch({ sort: s.key })}
              >
                {s.label}
              </button>
            ))}
          </div>
          <span className="muted product-count">共 {total} 项</span>
        </div>

        {error ? (
          <div className="state-card">
            <p>加载失败：{error}</p>
            <button className="btn" onClick={reload}>
              重试
            </button>
          </div>
        ) : loading ? (
          <div className="product-grid">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="product-skeleton" />
            ))}
          </div>
        ) : data && data.items.length > 0 ? (
          <>
            <div className="product-grid">
              {data.items.map((p) => (
                <ProductCard key={p.id} p={p} />
              ))}
            </div>
            {totalPages > 1 ? (
              <div className="pagination">
                <button
                  className="btn"
                  disabled={page <= 1}
                  onClick={() => q.setPage(page - 1)}
                >
                  上一页
                </button>
                <span className="muted">
                  第 {page} / {totalPages} 页
                </span>
                <button
                  className="btn"
                  disabled={page >= totalPages}
                  onClick={() => q.setPage(page + 1)}
                >
                  下一页
                </button>
              </div>
            ) : null}
          </>
        ) : (
          <div className="state-card">
            <p className="muted">没有符合条件的资源</p>
            {total === 0 ? (
              <button className="btn btn-ghost" onClick={resetFilters}>
                清空筛选
              </button>
            ) : null}
          </div>
        )}
      </section>
    </div>
  );
}
