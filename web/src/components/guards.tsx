/**
 * 路由守卫（02 §1 / 07 §4 红线 3）。
 *  - RequireAuth：未登录 → /login?redirect=<原路径>；登录后回跳。
 *  - RequireAdmin：未登录 → 登录回跳；非管理员 → /403（02 后台守卫）。
 * 守卫渲染 <Outlet/>，用于嵌套路由（/admin 区共用一个外壳布局）。
 */
import { useEffect, useRef, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import * as auth from "@/stores/auth";
import { fetchMe } from "@/api/auth";

function useRedirectPath(): string {
  const loc = useLocation();
  return `${loc.pathname}${loc.search}`;
}

/** 登录守卫：确保「已登录 + user 已加载」。首访用 /users/me 拉取身份（含 is_admin）。 */
export function RequireAuth() {
  const from = useRedirectPath();
  const [state, setState] = useState<"loading" | "ok" | "unauth">(
    auth.isLoggedIn() ? "loading" : "unauth",
  );
  const started = useRef(false);

  useEffect(() => {
    if (!auth.isLoggedIn()) {
      setState("unauth");
      return;
    }
    if (started.current) return;
    started.current = true;
    let alive = true;
    fetchMe()
      .then(() => alive && setState("ok"))
      .catch(() => alive && setState(auth.isLoggedIn() ? "ok" : "unauth"));
    // fetchMe 401 时拦截器已尝试刷新；刷新失败会跳登录。此处兜底：仍无 token 视为未登录。
    return () => {
      alive = false;
    };
  }, []);

  if (state === "unauth") return <Navigate to={`/login?redirect=${encodeURIComponent(from)}`} replace />;
  if (state === "loading") return <div className="page-placeholder">加载中…</div>;
  return <Outlet />;
}

/** 管理员守卫：在 RequireAuth 内层使用（保证 user 已就绪）。 */
export function RequireAdmin() {
  const from = useRedirectPath();
  const u = auth.getUser();
  if (!u) return <Navigate to={`/login?redirect=${encodeURIComponent(from)}`} replace />;
  if (!u.is_admin) return <Navigate to="/403" replace />;
  return <Outlet />;
}
