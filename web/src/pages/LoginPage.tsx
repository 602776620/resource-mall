/**
 * 登录（02 §1 /login，T03 起真实表单）。
 * 账号（用户名或邮箱）+ 密码；成功后按 ?redirect= 回跳（02 §3 守卫链路）。
 * 错误展示：统一错误体 {error:{code,message}} 优先；422 走 FastAPI 默认 {detail:[...]} 兜底。
 */
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { login } from "@/api/auth";
import { getErrorMessage } from "@/api/client";

export function LoginPage() {
  const [params] = useSearchParams();
  // 只允许站内相对路径回跳，防开放重定向
  const rawRedirect = params.get("redirect") || "/";
  const redirect = rawRedirect.startsWith("/") && !rawRedirect.startsWith("//") ? rawRedirect : "/";
  const navigate = useNavigate();

  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await login({ account: account.trim(), password });
      navigate(redirect, { replace: true });
    } catch (err) {
      setError(getErrorMessage(err, "登录失败，请稍后再试"));
      setBusy(false);
    }
  };

  return (
    <section className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>登录</h1>
        <label className="field">
          <span>账号（用户名或邮箱）</span>
          <input
            type="text"
            value={account}
            onChange={(e) => setAccount(e.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label className="field">
          <span>密码</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy ? "登录中…" : "登录"}
        </button>
        <p className="muted auth-alt">
          还没有账号？<Link to={`/register${redirect !== "/" ? `?redirect=${encodeURIComponent(redirect)}` : ""}`}>去注册</Link>
        </p>
      </form>
    </section>
  );
}
