import { Link } from "react-router-dom";

/** 404 页（02 §1）。 */
export function NotFoundPage() {
  return (
    <section className="page-placeholder">
      <h1>404 · 页面不存在</h1>
      <p className="muted">你访问的地址不存在。</p>
      <p>
        <Link to="/">返回首页</Link>
      </p>
    </section>
  );
}
