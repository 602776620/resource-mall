/**
 * 首页（02 §1 /）。精选（is_listed 按 created_at 倒序前 12）+ 分类入口 + 最新上架。
 * 金额/封面走 ProductCard 统一处理。
 */
import { useAsync } from "@/lib/useAsync";
import { getCategories, listProducts, type Category } from "@/api/products";
import { ProductCard } from "@/components/ProductCard";
import { Link } from "react-router-dom";

export function HomePage() {
  const featured = useAsync(() => listProducts({ page: 1, page_size: 12 }), []);
  const cats = useAsync<Category[]>(() => getCategories(), []);

  const items = featured.data?.items ?? [];

  return (
    <div className="home-page">
      {/* 分类入口 */}
      <section className="home-section">
        <div className="category-entry">
          <Link to="/products" className="cat-chip cat-chip-all">
            全部资源
          </Link>
          {cats.data?.map((c) => (
            <Link key={c.key} to={`/products?category=${c.key}`} className="cat-chip">
              {c.label}
            </Link>
          ))}
        </div>
      </section>

      {/* 精选 / 最新上架 */}
      <section className="home-section">
        <div className="section-head">
          <h2>最新上架</h2>
          <Link to="/products" className="muted">
            查看全部 →
          </Link>
        </div>

        {featured.error ? (
          <div className="state-card">
            <p>加载失败：{featured.error}</p>
            <button className="btn" onClick={featured.reload}>
              重试
            </button>
          </div>
        ) : featured.loading ? (
          <div className="product-grid">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="product-skeleton" />
            ))}
          </div>
        ) : items.length > 0 ? (
          <div className="product-grid">
            {items.map((p) => (
              <ProductCard key={p.id} p={p} />
            ))}
          </div>
        ) : (
          <div className="state-card">
            <p className="muted">暂无上架资源</p>
            <Link className="btn btn-ghost" to="/products">
              去逛逛
            </Link>
          </div>
        )}
      </section>
    </div>
  );
}
