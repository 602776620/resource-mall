/**
 * 商品详情（02 §1 /products/:id，无需登录）。
 * 封面、简介（后端已白名单过滤，直接渲染）、预览媒体区（图可点击放大 / 样本文件直下）、
 * 价格（原价划线）、标签、「立即购买」（未登录 → /login?redirect= 回跳，02 §2 主链）。
 * 加载失败/404（不存在或已下架）与 02 §3 统一：state-card + 返回资源列表。
 */
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { formatFen } from "@/lib/money";
import { categoryLabel } from "@/lib/categories";
import { isLoggedIn } from "@/stores/auth";
import { getProduct, mediaUrl, type MediaItem, type Product } from "@/api/products";
import { useAsync } from "@/lib/useAsync";

export function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data, loading, error } = useAsync(() => getProduct(id ?? ""), [id]);
  const [lightbox, setLightbox] = useState<MediaItem | null>(null);

  const p: Product | null = data;

  const buy = () => {
    if (!p) return;
    if (!isLoggedIn()) {
      // 未登录 → 跳登录，回跳目标为下单确认页（02 §1 详情页说明列）
      navigate(`/login?redirect=${encodeURIComponent(`/orders/create/${p.id}`)}`);
      return;
    }
    navigate(`/orders/create/${p.id}`);
  };

  return (
    <div className="detail-page">
      {error ? (
        <div className="state-card">
          <p>加载失败：{error}</p>
          <Link className="btn" to="/products">
            返回资源列表
          </Link>
        </div>
      ) : loading ? (
        <div className="detail-loading">
          <div className="skeleton-line" />
          <div className="skeleton-line wide" />
          <div className="detail-skeleton" />
        </div>
      ) : p ? (
        <div className="detail-grid">
          {/* 左：封面 + 预览图墙 */}
          <div className="detail-media">
            {p.cover_image ? (
              <img
                className="detail-cover"
                src={mediaUrl(p.cover_image)}
                alt={p.title}
                onClick={() => setLightbox({ kind: "image", url: mediaUrl(p.cover_image) })}
              />
            ) : (
              <div className="detail-cover detail-cover-empty muted">暂无封面</div>
            )}
            {p.preview_media.some((m) => m.kind === "image") ? (
              <div className="preview-thumbs">
                {p.preview_media
                  .filter((m) => m.kind === "image")
                  .map((m, i) => (
                    <img
                      key={i}
                      src={mediaUrl(m.url)}
                      alt={`预览 ${i + 1}`}
                      loading="lazy"
                      onClick={() => setLightbox({ ...m, url: mediaUrl(m.url) })}
                    />
                  ))}
              </div>
            ) : null}
          </div>

          {/* 右：信息 + 购买 */}
          <div className="detail-info">
            <span className="tag-category">{categoryLabel(p.category)}</span>
            <h1 className="detail-title">{p.title}</h1>
            {p.subtitle ? <p className="detail-subtitle muted">{p.subtitle}</p> : null}

            <div className="detail-price-row">
              <span className="detail-price">{formatFen(p.price_cents)}</span>
              {p.original_price_cents && p.original_price_cents > p.price_cents ? (
                <span className="detail-original muted">{formatFen(p.original_price_cents)}</span>
              ) : null}
            </div>

            {p.tags.length > 0 ? (
              <div className="detail-tags">
                {p.tags.map((t) => (
                  <span key={t} className="tag">
                    {t}
                  </span>
                ))}
              </div>
            ) : null}

            {/* 简介（后端白名单过滤后的 HTML，02 §1 渲染端白名单） */}
            {p.description ? (
              <div className="detail-desc" dangerouslySetInnerHTML={{ __html: p.description }} />
            ) : null}

            {/* 样本文件（未购买即可公开下载，02 §1） */}
            {p.preview_media.some((m) => m.kind === "file") ? (
              <div className="detail-samples">
                <h3>样本文件</h3>
                {p.preview_media
                  .filter((m) => m.kind === "file")
                  .map((m, i) => (
                    <a key={i} className="sample-link" href={mediaUrl(m.url)} download>
                      ⬇ {m.name ?? `样本文件 ${i + 1}`}
                    </a>
                  ))}
              </div>
            ) : null}

            <div className="detail-buy">
              <button className="btn btn-primary" onClick={buy}>
                立即购买
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* 图片放大弹层（图可放大，02 §1） */}
      {lightbox ? (
        <div className="lightbox" onClick={() => setLightbox(null)}>
          <img src={lightbox.url} alt="预览放大" />
          <span className="lightbox-hint muted">点击任意处关闭</span>
        </div>
      ) : null}
    </div>
  );
}
