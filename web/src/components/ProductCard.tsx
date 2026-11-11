/** 商品卡片（首页精选 / 列表页共用）。02 §4：金额 ¥+两位小数；cover 走签名短链。 */
import { Link } from "react-router-dom";
import { formatFen } from "@/lib/money";
import { mediaUrl, type Product } from "@/api/products";
import { CATEGORY_LABELS } from "@/lib/categories";

export function ProductCard({ p }: { p: Product }) {
  return (
    <Link to={`/products/${p.id}`} className="product-card">
      <div className="product-cover">
        {p.cover_image ? (
          <img src={mediaUrl(p.cover_image)} alt={p.title} loading="lazy" />
        ) : (
          <span className="product-cover-fallback">暂无封面</span>
        )}
      </div>
      <div className="product-card-body">
        <div className="product-title" title={p.title}>
          {p.title}
        </div>
        {p.subtitle ? <div className="product-subtitle muted">{p.subtitle}</div> : null}
        <div className="product-meta">
          <span className="tag-category">{CATEGORY_LABELS[p.category] ?? p.category}</span>
          {p.tags.slice(0, 3).map((t) => (
            <span key={t} className="tag">
              {t}
            </span>
          ))}
        </div>
        <div className="product-price-row">
          <span className="product-price">{formatFen(p.price_cents)}</span>
          {p.original_price_cents && p.original_price_cents > p.price_cents ? (
            <span className="product-original muted">
              {formatFen(p.original_price_cents)}
            </span>
          ) : null}
        </div>
      </div>
    </Link>
  );
}
