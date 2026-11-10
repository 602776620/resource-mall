/**
 * 路由表（02 §1 路由总表）。前台 `/` 区 + 后台 `/admin` 区（管理员守卫）。
 * 本切片（T02）各页为占位；真实交互自 T03 起逐页替换。
 */
import { createBrowserRouter, Navigate, Outlet, RouterProvider } from "react-router-dom";
import { RequireAdmin, RequireAuth } from "@/components/guards";

import { HomePage } from "@/pages/HomePage";
import { ProductsPage } from "@/pages/ProductsPage";
import { ProductDetailPage } from "@/pages/ProductDetailPage";
import { OrderCreatePage } from "@/pages/OrderCreatePage";
import { OrderPaymentPage } from "@/pages/OrderPaymentPage";
import { OrdersPage } from "@/pages/OrdersPage";
import { DownloadsPage } from "@/pages/DownloadsPage";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { ForbiddenPage } from "@/pages/errors/ForbiddenPage";
import { NotFoundPage } from "@/pages/errors/NotFoundPage";

import { AdminLayout } from "@/pages/admin/AdminLayout";
import { AdminOverviewPage } from "@/pages/admin/OverviewPage";
import { AdminProductsPage } from "@/pages/admin/ProductsPage";
import { AdminProductFormPage } from "@/pages/admin/ProductFormPage";
import { AdminOrdersPage } from "@/pages/admin/OrdersPage";
import { AdminReconcilePage } from "@/pages/admin/ReconcilePage";
import { AdminOrderDetailPage } from "@/pages/admin/OrderDetailPage";
import { AdminCouponsPage } from "@/pages/admin/CouponsPage";
import { AdminUsersPage } from "@/pages/admin/UsersPage";
import { AdminAuditPage } from "@/pages/admin/AuditPage";

/** 前台外壳：顶部导航（占位）+ 内容区。 */
function StoreLayout() {
  return (
    <div className="store-layout">
      <header className="store-nav">
        <a className="brand" href="/">
          资源商城
        </a>
        <nav>
          <a href="/">首页</a>
          <a href="/products">资源</a>
          <a href="/orders">我的订单</a>
          <a href="/downloads">下载中心</a>
        </nav>
      </header>
      <main className="store-main">
        <Outlet />
      </main>
    </div>
  );
}

const router = createBrowserRouter([
  {
    element: <StoreLayout />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/products", element: <ProductsPage /> },
      { path: "/products/:id", element: <ProductDetailPage /> },
      { path: "/login", element: <LoginPage /> },
      { path: "/register", element: <RegisterPage /> },
      // 需登录（02：下单确认 / 待支付 / 我的订单 / 下载中心）
      {
        element: <RequireAuth />,
        children: [
          { path: "/orders/create/:id", element: <OrderCreatePage /> },
          { path: "/orders/:orderNo/payment", element: <OrderPaymentPage /> },
          { path: "/orders", element: <OrdersPage /> },
          { path: "/downloads", element: <DownloadsPage /> },
        ],
      },
      { path: "/403", element: <ForbiddenPage /> },
      { path: "/404", element: <NotFoundPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
  // 后台：未登录 → /login?redirect=/admin；非管理员 → /403（02 §1 后台守卫）
  {
    path: "/admin",
    element: <RequireAuth />,
    children: [
      {
        element: <RequireAdmin />,
        children: [
          {
            element: <AdminLayout />,
            children: [
              { index: true, element: <AdminOverviewPage /> },
              { path: "products", element: <AdminProductsPage /> },
              { path: "products/new", element: <AdminProductFormPage /> },
              { path: "products/:id/edit", element: <AdminProductFormPage /> },
              { path: "orders", element: <AdminOrdersPage /> },
              { path: "orders/reconcile", element: <AdminReconcilePage /> },
              { path: "orders/:id", element: <AdminOrderDetailPage /> },
              { path: "coupons", element: <AdminCouponsPage /> },
              { path: "users", element: <AdminUsersPage /> },
              { path: "audit", element: <AdminAuditPage /> },
            ],
          },
        ],
      },
    ],
  },
  // 兜底：/admin 直接落空 → 重定向到 /admin（走守卫）
  { path: "/admin/*", element: <Navigate to="/admin" replace /> },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
