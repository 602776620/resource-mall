import { NavLink, Outlet } from "react-router-dom";
import { logout } from "@/api/client";
import * as auth from "@/stores/auth";

/** 后台外壳（02 §1 五区导航）。已保证在 RequireAuth+RequireAdmin 内（user 就绪）。 */
export function AdminLayout() {
  const u = auth.getUser();
  return (
    <div className="admin-layout">
      <aside className="admin-side">
        <div className="admin-brand">管理后台</div>
        <nav className="admin-nav">
          <NavLink to="/admin" end>
            概览
          </NavLink>
          <NavLink to="/admin/products">资源</NavLink>
          <NavLink to="/admin/orders">订单</NavLink>
          <NavLink to="/admin/orders/reconcile">核销工作台</NavLink>
          <NavLink to="/admin/coupons">券码</NavLink>
          <NavLink to="/admin/users">用户</NavLink>
          <NavLink to="/admin/audit">审计日志</NavLink>
        </nav>
        <div className="admin-foot">
          <span className="muted">{u?.username ?? ""}</span>
          <button type="button" onClick={() => void logout()}>
            退出
          </button>
        </div>
      </aside>
      <main className="admin-main">
        <Outlet />
      </main>
    </div>
  );
}
