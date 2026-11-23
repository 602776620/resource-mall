/**
 * 下载中心（02 §1 /downloads，需登录·本人）。
 * 已支付(paid)订单列表：商品、购买时间、剩余下载次数（7 天 50 次，05 §4）、
 * 配额窗口倒计时（以订单 created_at 为窗口起点）、「下载」按钮（调接口 302 触发）。
 *
 * 下载交互：按钮经 api/orders.triggerDownload 两步走——
 * ① fetch 签发接口（带 Bearer，跟随 302 拿到 /files/{token} 短链后立刻取消流，
 *    大文件不进内存）；② 顶层导航到短链触发浏览器原生附件下载（支持断点续传）。
 * 签名短链 15min 内可重复访问且不计配额（05 §4）。
 * 未支付/已撤销 → 403；超限 → 429（服务端校验链，04 §5）。
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listOrders, triggerDownload, type Order } from "@/api/orders";
import { useAsync } from "@/lib/useAsync";
import { formatFen } from "@/lib/money";
import { formatCountdown, formatTime } from "@/lib/time";

const QUOTA = 50; // 05 §4：7 天 50 次
const WINDOW_MS = 7 * 24 * 3600 * 1000;

export function DownloadsPage() {
  const { data, loading, error, reload } = useAsync(() => listOrders({ status: "paid", page_size: 100 }), []);

  // 每秒走时：配额窗口倒计时（02 §1「倒计时」列）
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const [downloading, setDownloading] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const items = data?.items ?? [];

  const onDownload = async (o: Order) => {
    setErr(null);
    setDownloading(o.order_no);
    try {
      // 先经鉴权接口拿签名短链，再顶层导航触发浏览器下载；短链 15min 有效
      await triggerDownload(o.order_no);
      // 顶层导航已接管（attachment 下载），页面仍在，复位按钮态
      setTimeout(() => setDownloading(null), 2000);
    } catch (e) {
      setDownloading(null);
      setErr(e instanceof Error ? e.message : "下载失败");
    }
  };

  return (
    <div className="downloads-page">
      <h1 className="page-title">下载中心</h1>
      <p className="muted downloads-hint">
        每个订单 7 天内可下载 {QUOTA} 次；下载链接 15 分钟内有效，过期请重新点击「下载」。
      </p>

      {err ? (
        <div className="state-card downloads-err">
          <p>⚠ {err}</p>
          <button className="btn" onClick={reload}>
            刷新订单
          </button>
        </div>
      ) : null}

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
        <div className="orders-list">
          {items.map((o) => {
            const used = o.download_count ?? 0;
            const remain = Math.max(0, QUOTA - used);
            // 配额窗口倒计时：以订单 created_at 为窗口起点（05 §4）
            const windowMs = new Date(o.created_at).getTime() + WINDOW_MS - now;
            const windowEnded = windowMs <= 0;
            return (
              <div key={o.order_no} className="order-card download-card">
                <div className="order-card-top">
                  <div className="order-product">
                    <span className="order-title">{o.product_title}</span>
                    <span className="muted order-no mono">{o.order_no}</span>
                  </div>
                  <span className="order-status order-status-paid">已完成</span>
                </div>

                <div className="order-card-mid">
                  <div className="order-meta-row">
                    <span className="muted">支付时间</span>
                    <span>{o.paid_at ? formatTime(o.paid_at) : formatTime(o.created_at)}</span>
                  </div>
                  <div className="order-meta-row">
                    <span className="muted">金额</span>
                    <span className="amount">{formatFen(o.amount_cents)}</span>
                  </div>
                  <div className="order-meta-row">
                    <span className="muted">剩余下载次数</span>
                    <span className={remain === 0 ? "download-quota-empty" : "download-quota"}>
                      {remain} / {QUOTA}（窗口剩余 {formatCountdown(windowMs)}）
                    </span>
                  </div>
                </div>

                <div className="order-card-actions">
                  {remain === 0 && windowEnded ? (
                    <span className="muted">
                      下载次数已用尽，7 天窗口已结束，如需再次下载请联系管理员
                    </span>
                  ) : null}
                  <button
                    className="btn btn-primary btn-sm"
                    disabled={remain <= 0 || downloading === o.order_no}
                    onClick={() => onDownload(o)}
                  >
                    {downloading === o.order_no ? "链接生成中…" : "下载"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="state-card">
          <p className="muted">还没有已完成的订单</p>
          <Link className="btn" to="/products">
            去逛逛
          </Link>
        </div>
      )}
    </div>
  );
}
