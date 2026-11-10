import { Link } from "react-router-dom";

/** 403 页（02 §1：带「登录」按钮）。 */
export function ForbiddenPage() {
  return (
    <section className="page-placeholder">
      <h1>403 · 无权限</h1>
      <p className="muted">你没有权限访问该页面（非管理员或用户被禁用）。</p>
      <p>
        <Link to="/login">去登录</Link>
      </p>
    </section>
  );
}
