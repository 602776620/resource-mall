import { Link } from "react-router-dom";

/** 注册页（占位骨架，T03 接真实表单 + register API）。 */
export function RegisterPage() {
  return (
    <section className="page-placeholder">
      <h1>注册</h1>
      <p className="muted">注册表单将在 T03 接入（用户名+邮箱+密码+确认）。</p>
      <p>
        <Link to="/login">去登录</Link>
      </p>
    </section>
  );
}
