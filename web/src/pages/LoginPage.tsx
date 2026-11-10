import { Link, useSearchParams } from "react-router-dom";

/**
 * 登录页（占位骨架，T03 接真实表单 + login API）。
 * 02 §1：账号(用户名或邮箱)+密码；成功按 ?redirect= 回跳。
 * 此处先解析并展示 redirect，便于验证守卫回跳链路。
 */
export function LoginPage() {
  const [params] = useSearchParams();
  const redirect = params.get("redirect");
  return (
    <section className="page-placeholder">
      <h1>登录</h1>
      <p className="muted">登录表单将在 T03 接入（账号/密码 + 回跳）。</p>
      {redirect ? (
        <p className="muted">
          登录后将跳转：<code>{redirect}</code>
        </p>
      ) : null}
      <p>
        <Link to="/register">去注册</Link>
      </p>
    </section>
  );
}
