/**
 * 核销工作台（02 §1 /admin/orders/reconcile，管理员；05 §2 SOP 落到界面）。
 * 队列 = pending 且 paid_submitted 非空，按提交时间正序（后端 submitted=true）。
 * 每行高亮三方：订单号 / 应付金额 / 用户支付说明；渠道单选 + 「核销」。
 * 二次确认弹层要求输入订单号后 6 位（09 §2-T06）；支持批量核销（勾选 + 统一渠道，逐单条件更新）。
 * 并发核销 409 → 按 SOP 步骤 6 提示检查审计日志，不重复操作。
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getErrorMessage } from "@/api/client";
import {
  confirmOrder,
  listAdminOrders,
  type AdminOrder,
} from "@/api/orders";
import { useAsync } from "@/lib/useAsync";
import { formatFen } from "@/lib/money";
import { formatTime } from "@/lib/time";

type Channel = "wechat" | "alipay";

const SOP_HINTS = [
  "三方比对（缺一不可）：收款记录金额 == 应付金额；渠道 == 用户选择；支付说明与收款记录可相互佐证。",
  "金额不一致 → 不得核销，先联系用户。",
  "发现重复核销（409）→ 检查审计日志确认首次核销，不重复操作。",
];

export function AdminReconcilePage() {
  const { data, loading, error, reload } = useAsync(
    () => listAdminOrders({ submitted: true, page: 1, page_size: 100 }),
    [],
  );

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [channel, setChannel] = useState<Channel>("wechat");
  // 单行核销时各自的渠道选择（默认跟随统一渠道）
  const [rowChannel, setRowChannel] = useState<Record<string, Channel>>({});
  const [confirmTarget, setConfirmTarget] = useState<AdminOrder[] | null>(null);
  const [confirmInput, setConfirmInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ ok: number; conflict: string[] }[] | null>(null);

  const items = data?.items ?? [];

  const last6 = (orderNo: string) => orderNo.slice(-6);

  const toggle = (orderNo: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(orderNo)) next.delete(orderNo);
      else next.add(orderNo);
      return next;
    });
  };
  const allChecked = items.length > 0 && items.every((o) => selected.has(o.order_no));
  const toggleAll = () => {
    setSelected(allChecked ? new Set() : new Set(items.map((o) => o.order_no)));
  };

  const openConfirm = (targets: AdminOrder[]) => {
    setResult(null);
    setConfirmInput("");
    setConfirmTarget(targets);
  };
  const closeConfirm = () => {
    setConfirmTarget(null);
    setConfirmInput("");
  };

  // 单核销：须输入该单后 6 位（09 §2-T06）；批量：勾选 + 统一渠道，逐单条件更新。
  const firstTarget = confirmTarget?.[0];
  const isSingle = confirmTarget?.length === 1;
  const suffixOk =
    !isSingle || (firstTarget ? last6(firstTarget.order_no) === confirmInput.trim().toUpperCase() : false);

  const confirm = async () => {
    if (!confirmTarget || !confirmTarget.length || !suffixOk) return;
    setSubmitting(true);
    let ok = 0;
    const conflicts: string[] = [];
    for (const o of confirmTarget) {
      const ch = rowChannel[o.order_no] ?? channel;
      try {
        await confirmOrder(o.order_no, ch);
        ok += 1;
      } catch (e) {
        // 409 CONFLICT → SOP 步骤 6：状态已变化，不重复操作
        conflicts.push(`${o.order_no}（${getErrorMessage(e)}）`);
      }
    }
    setResult([{ ok, conflict: conflicts }]);
    setSubmitting(false);
    if (ok > 0) {
      setSelected(new Set());
      reload();
    }
  };

  const totalAmount = useMemo(
    () => items.filter((o) => selected.has(o.order_no)).reduce((s, o) => s + o.amount_cents, 0),
    [items, selected],
  );

  const conflictList = result?.[0]?.conflict ?? [];

  return (
    <section className="reconcile-page">
      <h1>核销工作台</h1>
      <div className="sop-hints">
        <h3>核销 SOP（人工操作强制规范）</h3>
        <ol>
          {SOP_HINTS.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      </div>

      <div className="reconcile-toolbar">
        <label className="check-label">
          <input type="checkbox" checked={allChecked} onChange={toggleAll} />
          全选
        </label>
        <span className="muted">统一渠道：</span>
        <select className="input channel-select" value={channel} onChange={(e) => setChannel(e.target.value as Channel)}>
          <option value="wechat">微信</option>
          <option value="alipay">支付宝</option>
        </select>
        <span className="muted">已选 {selected.size} 单 · 合计 {formatFen(totalAmount)}</span>
        <button
          className="btn btn-primary"
          disabled={selected.size === 0}
          onClick={() => openConfirm(items.filter((o) => selected.has(o.order_no)))}
        >
          批量核销
        </button>
      </div>

      {error ? (
        <div className="state-card">
          <p>加载失败：{error}</p>
          <button className="btn" onClick={reload}>重试</button>
        </div>
      ) : loading ? (
        <div className="detail-loading">
          <div className="skeleton-line" />
          <div className="skeleton-line wide" />
        </div>
      ) : items.length > 0 ? (
        <table className="admin-table reconcile-table">
          <thead>
            <tr>
              <th></th>
              <th>订单号</th>
              <th>用户</th>
              <th>应付金额</th>
              <th>支付说明（佐证）</th>
              <th>提交时间</th>
              <th>渠道</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((o) => (
              <tr key={o.order_no}>
                <td>
                  <input
                    type="checkbox"
                    checked={selected.has(o.order_no)}
                    onChange={() => toggle(o.order_no)}
                  />
                </td>
                <td className="mono highlight-cell">{o.order_no}</td>
                <td>{o.username ?? `#${o.user_id}`}</td>
                <td className="amount highlight-cell">{formatFen(o.amount_cents)}</td>
                <td className="note-cell highlight-cell" title={o.paid_note ?? ""}>
                  {o.paid_note ?? "—"}
                </td>
                <td className="muted">{formatTime(o.paid_submitted_at)}</td>
                <td>
                  <select
                    className="input"
                    value={rowChannel[o.order_no] ?? channel}
                    onChange={(e) =>
                      setRowChannel((prev) => ({ ...prev, [o.order_no]: e.target.value as Channel }))
                    }
                  >
                    <option value="wechat">微信</option>
                    <option value="alipay">支付宝</option>
                  </select>
                </td>
                <td>
                  <button className="btn btn-sm" onClick={() => openConfirm([o])}>
                    核销
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="state-card">
          <p className="muted">暂无待核销订单（队列为空）</p>
          <Link className="btn" to="/admin/orders">返回订单列表</Link>
        </div>
      )}

      {confirmTarget ? (
        <div className="modal-mask" onClick={closeConfirm}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-title">核销二次确认</h3>
            <p className="muted modal-desc">
              {isSingle && firstTarget
                ? `请核对并输入订单号 ${firstTarget.order_no} 的后 6 位以确认核销。`
                : `批量核销 ${confirmTarget.length} 单：请确认已对每单完成三方比对。`}
            </p>
            <input
              className="input"
              placeholder="订单号后 6 位"
              maxLength={6}
              value={confirmInput}
              onChange={(e) => setConfirmInput(e.target.value.toUpperCase())}
            />
            {conflictList.length > 0 ? (
              <p className="form-error">
                以下订单未能核销（状态已变化 / 6 位不符，按 SOP 检查审计日志）：
                {conflictList.join("、")}
              </p>
            ) : null}
            <div className="modal-actions">
              <button className="btn" onClick={closeConfirm}>取消</button>
              <button
                className="btn btn-primary"
                disabled={submitting || (isSingle ? !suffixOk : false)}
                onClick={() => void confirm()}
              >
                {submitting ? "核销中…" : "确认核销"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
