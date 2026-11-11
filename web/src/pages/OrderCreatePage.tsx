/**
 * 下单确认页（02 §1 /orders/create/:id，需登录）。
 * 商品摘要 + 券码输入（输入即调预检接口显示抵扣，04 §4）+ 应付金额 + 「提交订单」。
 * 03 铁律 3：金额全由服务端算，前端只展示预检结果；提交只传 product_id + coupon_code。
 */
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getErrorMessage } from "@/api/client";
import { checkCoupon, createOrder, type CouponCheck } from "@/api/orders";
import { getProduct, mediaUrl, type Product } from "@/api/products";
import { useAsync } from "@/lib/useAsync";
import { formatFen } from "@/lib/money";

export function OrderCreatePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: p, loading, error } = useAsync(() => getProduct(id ?? ""), [id]);

  const [couponCode, setCouponCode] = useState("");
  const [check, setCheck] = useState<CouponCheck | null>(null);
  const [checkState, setCheckState] = useState<"idle" | "checking" | "done">("idle");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // 输入即预检（02 §1：输入即调校验接口显示抵扣）
  useEffect(() => {
    const code = couponCode.trim();
    if (!code) {
      setCheck(null);
      setCheckState("idle");
      return;
    }
    setCheckState("checking");
    let alive = true;
    const t = setTimeout(() => {
      checkCoupon(code)
        .then((c) => {
          if (!alive) return;
          setCheck(c);
          setCheckState("done");
        })
        .catch(() => {
          if (!alive) return;
          setCheck({ valid: false });
          setCheckState("done");
        });
    }, 400);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [couponCode]);

  const product = p as Product | null;
  const original = product?.price_cents ?? 0;
  const discount =
    check?.valid && check.type && check.value != null ? discountOf(check, original) : 0;
  const payable = Math.max(0, original - discount);

  const submit = async () => {
    if (!product) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const order = await createOrder(product.id, couponCode.trim() || undefined);
      navigate(`/orders/${order.order_no}/payment`);
    } catch (e) {
      setSubmitError(getErrorMessage(e, "下单失败"));
    } finally {
      setSubmitting(false);
    }
  };

  if (error) {
    return (
      <div className="state-card">
        <p>加载失败：{error}</p>
        <Link className="btn" to="/products">
          返回资源列表
        </Link>
      </div>
    );
  }
  if (loading || !product) {
    return (
      <div className="detail-loading">
        <div className="skeleton-line" />
        <div className="skeleton-line wide" />
      </div>
    );
  }

  return (
    <div className="order-create">
      <h1 className="page-title">确认订单</h1>

      <div className="order-create-grid">
        {/* 左：商品摘要 */}
        <div className="card order-summary">
          <h3 className="card-title">购买内容</h3>
          <div className="order-summary-item">
            {product.cover_image ? (
              <img className="order-summary-cover" src={mediaUrl(product.cover_image)} alt={product.title} />
            ) : (
              <div className="order-summary-cover order-summary-cover-empty muted">—</div>
            )}
            <div>
              <p className="order-summary-title">{product.title}</p>
              <p className="muted order-summary-meta">
                标价 <span className="amount">{formatFen(original)}</span>
              </p>
            </div>
          </div>
        </div>

        {/* 右：券码 + 应付 + 提交 */}
        <div className="card order-form">
          <h3 className="card-title">优惠券</h3>
          <input
            className="input"
            placeholder="输入券码（选填，C 开头）"
            value={couponCode}
            maxLength={32}
            onChange={(e) => setCouponCode(e.target.value.toUpperCase())}
          />
          {checkState === "checking" ? <p className="muted check-hint">校验中…</p> : null}
          {checkState === "done" && check ? (
            check.valid ? (
              <p className="check-hint check-ok">
                ✓ 有效：{check.type === "percent" ? `${check.value}% 折扣` : `立减 ${formatFen(check.value ?? 0)}`}
                ，本单抵扣 <span className="amount amount-discount">{formatFen(discount)}</span>
              </p>
            ) : (
              <p className="check-hint check-bad">✗ 券码无效（不存在/已停用/超量/过期）</p>
            )
          ) : null}

          <div className="order-payable">
            <div className="payable-row">
              <span className="muted">商品金额</span>
              <span className="amount">{formatFen(original)}</span>
            </div>
            {discount > 0 ? (
              <div className="payable-row">
                <span className="muted">券抵扣</span>
                <span className="amount amount-discount">-{formatFen(discount)}</span>
              </div>
            ) : null}
            <div className="payable-row payable-total">
              <span>应付金额</span>
              <span className="amount payable-amount">
                {payable === 0 ? "¥0.00（全额抵扣）" : formatFen(payable)}
              </span>
            </div>
          </div>

          {submitError ? <p className="form-error">{submitError}</p> : null}

          <button className="btn btn-primary btn-block" onClick={submit} disabled={submitting}>
            {submitting ? "提交中…" : payable === 0 ? "提交订单（0 元单）" : "提交订单"}
          </button>
          <p className="muted order-create-hint">提交后 30 分钟内有效，请前往待支付页完成支付。</p>
        </div>
      </div>
    </div>
  );
}

/** 预检结果 → 抵扣额（与 03 铁律 3 同公式，仅用于展示；最终以后端下单为准）。 */
function discountOf(check: CouponCheck, originalCents: number): number {
  if (!check.type || check.value == null) return 0;
  if (check.type === "percent") return Math.floor((originalCents * check.value) / 100);
  return Math.min(check.value, originalCents);
}
