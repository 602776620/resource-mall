import { Link } from "react-router-dom";

export function AdminOrdersPage() {
  return (
    <section className="page-placeholder">
      <h1>订单管理</h1>
      <p className="muted">订单 Tab + 搜索 + 详情抽屉（T06 实现）。</p>
      <Link to="/admin/orders/reconcile">进入核销工作台 →</Link>
    </section>
  );
}
