import { Link } from "react-router-dom";

export function AdminProductsPage() {
  return (
    <section className="page-placeholder">
      <h1>资源管理</h1>
      <p className="muted">资源表格 + 编辑/上下架/删除（T04 实现）。</p>
      <Link to="/admin/products/new">+ 新建资源</Link>
    </section>
  );
}
