/**
 * 待支付页（02 §1 /orders/:orderNo/payment，需登录·本人）。
 * 收款码大图（按所选渠道占位）+ 金额 + 订单号（可复制）+ 30min 倒计时 +
 * 状态轮询（5s，02 §5 后台核销无实时推送，靠轮询感知 paid）+「我已付款」弹层（说明必填≥5字）+ 页尾取消。
 * 倒计时归零 → 自动调取消 + 提示刷新状态（02 §4 交互规则）。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getErrorMessage } from "@/api/client";
import { cancelOrder, getOrder, submitPaid, type Order } from "@/api/orders";
import { formatFen } from "@/lib/money";
import { formatCountdown, formatTime } from "@/lib/time";

const POLL_MS = 5000; // 02 §1/§5：5s 轮询

export function OrderPaymentPage() {
  const { orderNo } = useParams<{ orderNo: string }>();

  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [channel, setChannel] = useState<"wechat" | "alipay">("wechat");

  // 我已付款弹层
  const [showPaidModal, setShowPaidModal] = useState(false);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [paidError, setPaidError] = useState<string | null>(null);

  // 取消
  const [cancelling, setCancelling] = useState(false);

  const load = useCallback(async () => {
    if (!orderNo) return;
    try {
      setOrder(await getOrder(orderNo));
      setError(null);
    } catch (e) {
      setError(getErrorMessage(e, "订单加载失败"));
    }
  }, [orderNo]);

  // 首次 + 5s 轮询（02 §5）
  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  // 倒计时走秒
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const remainMs = order ? new Date(order.expire_at).getTime() - now : 0;

  // 倒计时归零 → 自动取消 + 提示（02 §4）
  const autoCancelledRef = useRef(false);
  useEffect(() => {
    if (!order) return;
    if (
      order.pay_status === "pending" &&
      remainMs <= 0 &&
      !autoCancelledRef.current
    ) {
      autoCancelledRef.current = true;
      if (orderNo) {
        cancelOrder(orderNo)
          .then(() => void load())
          .catch(() => void load());
      }
    }
  }, [remainMs, order, orderNo, load]);

  // 轮询感知到 paid → 引导下载中心（02 §1）
  if (order?.pay_status === "paid") {
    return (
      <div className="state-card payment-done">
        <div className="payment-done-icon">✓</div>
        <h1 className="page-title">支付已确认</h1>
        <p className="muted">管理员已核销，订单进入已完成状态。</p>
        <div className="payment-done-actions">
          <Link className="btn btn-primary" to="/downloads">
            去下载中心
          </Link>
          <Link className="btn" to="/orders">
            我的订单
          </Link>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="state-card">
        <p>加载失败：{error}</p>
        <Link className="btn" to="/orders">
          返回我的订单
        </Link>
      </div>
    );
  }
  if (!order) {
    return (
      <div className="detail-loading">
        <div className="skeleton-line wide" />
        <div className="skeleton-line" />
      </div>
    );
  }

  const isCancelled = order.pay_status === "cancelled";
  const isRevoked = order.pay_status === "revoked";
  const isExpired = remainMs <= 0;
  const zeroAmount = order.amount_cents === 0;

  const copyOrderNo = () => {
    void navigator.clipboard?.writeText(order.order_no).catch(() => {});
  };

  const submitPaidNote = async () => {
    if (!orderNo) return;
    setSubmitting(true);
    setPaidError(null);
    try {
      await submitPaid(orderNo, note.trim());
      setShowPaidModal(false);
      await load();
    } catch (e) {
      setPaidError(getErrorMessage(e, "提交失败"));
    } finally {
      setSubmitting(false);
    }
  };

  const doCancel = async () => {
    if (!orderNo) return;
    if (!window.confirm("确定取消该订单？取消后不可恢复。")) return;
    setCancelling(true);
    try {
      await cancelOrder(orderNo);
      await load();
    } catch (e) {
      window.alert(getErrorMessage(e, "取消失败"));
    } finally {
      setCancelling(false);
    }
  };

  return (
    <div className="payment-page">
      <h1 className="page-title">待支付</h1>

      {isCancelled || isRevoked ? (
        <div className="state-card">
          <p>{isCancelled ? "该订单已取消。" : "该订单已撤销（请联系管理员）"}</p>
          <Link className="btn" to="/orders">
            返回我的订单
          </Link>
        </div>
      ) : (
        <div className="payment-grid">
          {/* 左：收款码（按渠道占位） */}
          <div className="card payment-qr">
            <div className="payment-channel-tabs">
              <button
                className={channel === "wechat" ? "channel-tab active" : "channel-tab"}
                onClick={() => setChannel("wechat")}
              >
                微信
              </button>
              <button
                className={channel === "alipay" ? "channel-tab active" : "channel-tab"}
                onClick={() => setChannel("alipay")}
              >
                支付宝
              </button>
            </div>
            <div className="qr-placeholder">
              <div className="qr-mock" />
              <span className="muted qr-hint">{channel === "wechat" ? "微信收款码" : "支付宝收款码"}（示意）</span>
            </div>
            <p className="muted payment-tip">
              请用 <strong>{channel === "wechat" ? "微信" : "支付宝"}</strong> 扫码支付
              <span className="amount payable-amount">{formatFen(order.amount_cents)}</span>
              ，支付后点右侧「我已付款」并提交支付说明。
            </p>
            {zeroAmount ? (
              <p className="payment-zero">
                ✓ 已全额抵扣（0 元单），无需扫码，直接点「我已付款」，说明填「0元单」即可。
              </p>
            ) : null}
          </div>

          {/* 右：订单信息 + 操作 */}
          <div className="card payment-info">
            <div className="payment-row">
              <span className="muted">订单号</span>
              <span className="amount mono order-no">
                {order.order_no}
                <button className="copy-btn" onClick={copyOrderNo} title="复制订单号">
                  复制
                </button>
              </span>
            </div>
            <div className="payment-row">
              <span className="muted">商品</span>
              <span>{order.product_title}</span>
            </div>
            <div className="payment-row">
              <span className="muted">应付金额</span>
              <span className="amount payable-amount">{formatFen(order.amount_cents)}</span>
            </div>
            <div className="payment-row">
              <span className="muted">下单时间</span>
              <span>{formatTime(order.created_at)}</span>
            </div>
            <div className="payment-row">
              <span className="muted">支付倒计时</span>
              <span className={`countdown ${isExpired ? "countdown-ended" : ""}`}>
                {formatCountdown(remainMs)}
              </span>
            </div>
            {order.paid_submitted_at ? (
              <div className="payment-row">
                <span className="muted">已提交支付说明</span>
                <span className="paid-submitted">
                  ✓ {formatTime(order.paid_submitted_at)} · {order.paid_note}
                </span>
              </div>
            ) : null}

            <div className="payment-actions">
              <button
                className="btn btn-primary"
                onClick={() => {
                  setShowPaidModal(true);
                  setPaidError(null);
                  if (!note && zeroAmount) setNote("0元单");
                }}
                disabled={!!order.paid_submitted_at || isExpired}
              >
                {order.paid_submitted_at ? "已提交，等待核销" : "我已付款"}
              </button>
              {!order.paid_submitted_at && !isExpired ? (
                <button className="btn btn-danger" onClick={doCancel} disabled={cancelling}>
                  {cancelling ? "取消中…" : "取消订单"}
                </button>
              ) : null}
            </div>
            <p className="muted payment-poll-hint">页面每 5 秒自动刷新核销状态。</p>
          </div>
        </div>
      )}

      {/* 我已付款弹层（说明必填≥5字，05 §2 佐证） */}
      {showPaidModal ? (
        <div className="modal-mask" onClick={() => setShowPaidModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-title">提交支付说明</h3>
            <p className="muted modal-desc">
              请填写可佐证支付的说明（≥5 字），例如「17:20 支付宝 尾号 1234 支付」。管理员将据此核对收款记录。
            </p>
            <textarea
              className="input"
              rows={3}
              maxLength={500}
              placeholder="支付时间 / 渠道 / 尾号等佐证信息"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            {note.trim().length < 5 ? <p className="form-hint">说明至少 5 个字</p> : null}
            {paidError ? <p className="form-error">{paidError}</p> : null}
            <div className="modal-actions">
              <button className="btn" onClick={() => setShowPaidModal(false)}>
                取消
              </button>
              <button
                className="btn btn-primary"
                onClick={submitPaidNote}
                disabled={submitting || note.trim().length < 5}
              >
                {submitting ? "提交中…" : "确认已付款"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
