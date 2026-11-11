/**
 * 我的订单（02 §1 /orders，需登录·本人）。
 * 状态 Tab：全部/待支付/待核销(pending且已提交)/已完成(paid)/已取消/已撤销；
 * 列：商品、订单号、金额、状态、时间、操作（去支付/去下载/复制订单号）。
 * 后端 list_user_orders 只按 pay_status 过滤；待核销 = pending 中 paid_submitted_at 非空，
 * 故 Tab 映射到服务端 status + 客户端二次切分（pending 订单是临时的，单页足够）。
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listOrders, type Order, type PayStatus } from "@/api/orders";
import { useAsync } from "@/lib/useAsync";
import { useQueryState } from "@/lib/useQueryState";
import { formatFen } from "@/lib/money";
import { formatCountdown, formatTime } from "@/lib/time";

type Tab = "all" | "pending" | "reconciling" | "paid" | "cancelled" | "revoked";

const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "pending", label: "待支付" },
  { key: "reconciling", label: "待核销" },
  { key: "paid", label: "已完成" },
  { key: "cancelled", label: "已取消" },
  { key: "revoked", label: "已撤销" },
];

const STATUS_LABEL: Record<PayStatus, string> = {
  pending: "待支付",
  paid: "已完成",
  cancelled: "已取消",
  revoked: "已撤销",
};

/** Tab → 服务端 pay_status（reconciling 与 pending 同属服务端 pending，客户端再切分）。 */
function tabToServerStatus(tab: Tab): PayStatus | undefined {
  if (tab === "all") return undefined;
  if (tab === "reconciling") return "pending";
  return tab; // pending / paid / cancelled / revoked
}

function statusLabel(o: Order): string {
  return o.pay_status === "pending" && o.paid_submitted_at ? "待核销" : STATUS_LABEL[o.pay_status];
}

export function OrdersPage() {
  const q = useQueryState();
  const tab = (q.get("tab") || "all") as Tab;
  const page = Number(q.get("page") || 1);

  const [now, setNow] = useState(() => Date.now());
  const [copied, setCopied] = useState<string | null>(null);

  // 每秒走时：待支付订单倒计时显示。
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const params = {
    status: tabToServerStatus(tab),
    page,
    page_size: 20,
  };

  const { data, loading, error, reload } = useAsync(() => listOrders(params), [
    JSON.stringify(params),
  ]);

  // 服务端返回后，按 Tab 客户端二次切分 pending。
  const raw = data?.items ?? [];
  const items =
    tab === "pending"
      ? raw.filter((o) => !o.paid_submitted_at)
      : tab === "reconciling"
        ? raw.filter((o) => o.paid_submitted_at)
        : raw;

  const total = data?.total ?? 0;
  const pageSize = data?.page_size ?? 20;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const copyOrderNo = (no: string) => {
    void navigator.clipboard?.writeText(no).catch(() => {});
    setCopied(no);
    setTimeout(() => setCopied(null), 1500);
  };

  const setTab = (t: Tab) => q.patch({ tab: t === "all" ? "" : t, page: "" });

  return (
    <div className="orders-page">
      <h1 className="page-title">我的订单</h1>

      <div className="orders-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={tab === t.key ? "tab active" : "tab"}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error ? (
        <div className="state-card">
          <p>加载失败：{error}</p>
          <button className="btn" onClick={reload}>
            重试
          </button>
        </div>
      ) : loading ? (
        <div className="orders-loading">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="order-card order-card-skeleton">
              <div className="skeleton-line" />
              <div className="skeleton-line wide" />
            </div>
          ))}
        </div>
      ) : items.length > 0 ? (
        <>
          <div className="orders-list">
            {items.map((o) => {
              const remainMs = new Date(o.expire_at).getTime() - now;
              const isPendingPay = o.pay_status === "pending" && !o.paid_submitted_at;
              const isReconciling = o.pay_status === "pending" && !!o.paid_submitted_at;
              const expired = isPendingPay && remainMs <= 0;
              return (
                <div key={o.order_no} className="order-card">
                  <div className="order-card-top">
                    <div className="order-product">
                      <span className="order-title">{o.product_title}</span>
                      <span className="muted order-no mono" title="点击复制">
                        {o.order_no}
                      </span>
                    </div>
                    <span className={`order-status order-status-${o.pay_status}`}>
                      {statusLabel(o)}
                    </span>
                  </div>

                  <div className="order-card-mid">
                    <div className="order-meta-row">
                      <span className="muted">金额</span>
                      <span className="amount">
                        {formatFen(o.amount_cents)}
                        {o.discount_cents > 0 ? (
                          <>
                            {" "}
                            <span className="amount-original">{formatFen(o.original_cents)}</span>
                          </>
                        ) : null}
                      </span>
                    </div>
                    <div className="order-meta-row">
                      <span className="muted">下单时间</span>
                      <span>{formatTime(o.created_at)}</span>
                    </div>
                    {isPendingPay ? (
                      <div className="order-meta-row">
                        <span className="muted">支付倒计时</span>
                        <span className={`countdown ${expired ? "countdown-ended" : ""}`}>
                          {formatCountdown(remainMs)}
                        </span>
                      </div>
                    ) : null}
                    {isReconciling ? (
                      <div className="order-meta-row">
                        <span className="muted">已提交说明</span>
                        <span className="paid-submitted">✓ {o.paid_note}</span>
                      </div>
                    ) : null}
                  </div>

                  <div className="order-card-actions">
                    {o.order_no ? (
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => copyOrderNo(o.order_no)}
                      >
                        {copied === o.order_no ? "已复制" : "复制订单号"}
                      </button>
                    ) : null}
                    {isPendingPay ? (
                      <Link
                        className="btn btn-primary btn-sm"
                        to={`/orders/${o.order_no}/payment`}
                      >
                        {expired ? "已超时" : "去支付"}
                      </Link>
                    ) : null}
                    {isReconciling ? (
                      <span className="muted order-waiting">等待管理员核销…</span>
                    ) : null}
                    {o.pay_status === "paid" ? (
                      <Link className="btn btn-primary btn-sm" to="/downloads">
                        去下载
                      </Link>
                    ) : null}
                  </div>
                </div>
              );
            })}
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
          <p className="muted">没有相关订单</p>
          <Link className="btn" to="/products">
            去逛逛
          </Link>
        </div>
      )}
    </div>
  );
}
