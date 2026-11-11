/**
 * 注册（02 §1 /register，T03 起真实表单）。
 * 用户名+邮箱+密码+确认；服务端约束（04 §3）：用户名/邮箱二选一必填，
 * 用户名 3~32 位字母数字下划线，密码 8~64 位且同时含字母和数字。
 * 成功后自动登录并按 ?redirect= 回跳。
 */
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { register } from "@/api/auth";
import { getErrorMessage } from "@/api/client";

export function RegisterPage() {
  const [params] = useSearchParams();
  // 只允许站内相对路径回跳，防开放重定向
  const rawRedirect = params.get("redirect") || "/";
  const redirect = rawRedirect.startsWith("/") && !rawRedirect.startsWith("//") ? rawRedirect : "/";
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await register({
        username: username.trim() || undefined,
        email: email.trim() || undefined,
        password,
        password_confirm: passwordConfirm,
      });
      navigate(redirect, { replace: true });
    } catch (err) {
      setError(getErrorMessage(err, "注册失败，请稍后再试"));
      setBusy(false);
    }
  };

  return (
    <section className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>注册</h1>
        <label className="field">
          <span>用户名（3~32 位字母/数字/下划线）</span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            placeholder="与邮箱至少填一项"
          />
        </label>
        <label className="field">
          <span>邮箱</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            placeholder="与用户名至少填一项"
          />
        </label>
        <label className="field">
          <span>密码（8~64 位，含字母和数字）</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            required
          />
        </label>
        <label className="field">
          <span>确认密码</span>
          <input
            type="password"
            value={passwordConfirm}
            onChange={(e) => setPasswordConfirm(e.target.value)}
            autoComplete="new-password"
            required
          />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy ? "注册中…" : "注册"}
        </button>
        <p className="muted auth-alt">
          已有账号？<Link to={`/login${redirect !== "/" ? `?redirect=${encodeURIComponent(redirect)}` : ""}`}>去登录</Link>
        </p>
      </form>
    </section>
  );
}
