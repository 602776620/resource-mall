/**
 * 订单域请求函数（04 §5 用户 / §6 管理员核销）。统一经 client.http。
 * 金额以「分」存；分↔元换算由 lib/money 负责（07 §4 红线 2）。
 */
import { http, getErrorMessage } from "@/api/client";
import type { Paginated } from "@/api/types";

export type PayStatus = "pending" | "paid" | "revoked" | "cancelled";

/** 订单（04 §5 响应模型；管理端多 user_id/username/email）。 */
export interface Order {
  order_no: string;
  product_id: number;
  product_title: string;
  amount_cents: number;
  original_cents: number;
  coupon_code: string | null;
  discount_cents: number;
  pay_status: PayStatus;
  pay_channel: "wechat" | "alipay" | null;
  paid_submitted_at: string | null;
  paid_note: string | null;
  paid_at: string | null;
  expire_at: string;
  created_at: string;
  /** 配额窗口（7 天）内已签发下载次数（05 §4，下载中心展示剩余次数）。 */
  download_count: number;
}

/** 订单详情（多文件/撤销字段）。 */
export interface OrderDetail extends Order {
  file_name: string | null;
  file_size: number | null;
  revoked_at: string | null;
  revoke_reason: string | null;
}

/** 管理端订单（多用户信息）。 */
export interface AdminOrder extends Order {
  user_id: number;
  username: string | null;
  email: string | null;
}

export interface AdminOrderDetail extends AdminOrder {
  file_name: string | null;
  file_size: number | null;
  download_logs: { ip: string | null; user_agent: string | null; created_at: string }[];
}

export interface ListOrdersParams {
  status?: PayStatus;
  page?: number;
  page_size?: number;
}

export interface AdminOrdersParams {
  status?: PayStatus;
  submitted?: boolean;
  order_no?: string;
  user?: string;
  page?: number;
  page_size?: number;
}

export interface CouponCheck {
  valid: boolean;
  type?: "fixed" | "percent";
  value?: number;
}

/** 券码有效性预检（04 §4）。只回 valid + 类型/值，不暴露已用/原因明细。 */
export function checkCoupon(code: string): Promise<CouponCheck> {
  return http.get<CouponCheck>(`/coupons/${encodeURIComponent(code.trim())}`).then((r) => r.data);
}

/** 下单（服务端算价，03 铁律 3）。201。 */
export function createOrder(product_id: number, coupon_code?: string): Promise<Order> {
  return http
    .post<Order>("/orders", { product_id, coupon_code: coupon_code || null })
    .then((r) => r.data);
}

/** 我的订单（created_at 倒序）。 */
export function listOrders(params: ListOrdersParams = {}): Promise<Paginated<Order>> {
  return http.get<Paginated<Order>>("/orders", { params }).then((r) => r.data);
}

/** 订单详情（仅本人，他人 404）。 */
export function getOrder(orderNo: string): Promise<OrderDetail> {
  return http.get<OrderDetail>(`/orders/${orderNo}`).then((r) => r.data);
}

/** 取消（pending→cancelled）。 */
export function cancelOrder(orderNo: string): Promise<Order> {
  return http.post<Order>(`/orders/${orderNo}/cancel`).then((r) => r.data);
}

/** 我已付款（提交支付说明，进入核销队列）。note ≥5 字。 */
export function submitPaid(orderNo: string, note: string): Promise<Order> {
  return http.post<Order>(`/orders/${orderNo}/paid-submitted`, { note }).then((r) => r.data);
}

/**
 * 触发下载（04 §5 / T07）：GET /orders/{no}/download → 302 → /files/{token}。
 *
 * 为什么不用 window.location 直接导航？该签发接口需要 Bearer 头（仅本人），
 * 顶层导航无法带 Authorization → 会 401。故分两步：
 *   1. fetch（走 axios 同款 Authorization 头，follow 302）拿到签名短链 URL，并读取 HTTP 状态；
 *      拿到后立即 cancel 响应体（不读文件内容，避免大文件进内存）。
 *   2. 用拿到的 /files/{token} 做顶层导航：无鉴权、流式直写磁盘（浏览器原生，支持断点续传），
 *      Content-Disposition: attachment 触发下载而非跳转，页面不会被替换。
 * 返回 403（未支付/已撤销）/429（超限）/503 时抛错，由调用方提示（不打开新页显示裸 JSON）。
 */
export async function triggerDownload(orderNo: string): Promise<void> {
  const { getToken } = await import("@/stores/auth");
  const t = getToken();
  const res = await fetch(
    `/api/v1/orders/${encodeURIComponent(orderNo)}/download`,
    { headers: t ? { Authorization: `Bearer ${t.access_token}` } : {} },
  );
  // 读 JSON 错误体（非 2xx/302 时后端返回 {error:{...}}）
  if (!res.ok) {
    let msg = `下载失败（${res.status}）`;
    try {
      const body = (await res.json()) as { error?: { message?: string } };
      if (body?.error?.message) msg = body.error.message;
    } catch {
      /* 非 JSON 错误体，保留默认文案 */
    }
    throw new Error(msg);
  }
  // res.url 为 302 跟随后的最终签名短链（/api/v1/files/{token}，浏览器侧 origin=前端）。
  // 立即取消该流：不读文件内容（大文件不进内存），真正的下载由下方顶层导航完成
  // （签名短链重复访问不计配额，05 §4）。
  void res.body?.cancel();
  window.location.assign(res.url);
}

// ---- 管理端（04 §6，核销工作台）----

export function listAdminOrders(params: AdminOrdersParams = {}): Promise<Paginated<AdminOrder>> {
  return http.get<Paginated<AdminOrder>>("/admin/orders", { params }).then((r) => r.data);
}

export function getAdminOrder(orderNo: string): Promise<AdminOrderDetail> {
  return http.get<AdminOrderDetail>(`/admin/orders/${orderNo}`).then((r) => r.data);
}

/** 核销（pending→paid 条件更新）。并发/已取消 → 409。 */
export function confirmOrder(
  orderNo: string,
  pay_channel: "wechat" | "alipay",
  note?: string,
): Promise<Order> {
  return http
    .post<Order>(`/admin/orders/${orderNo}/confirm`, { pay_channel, note: note || null })
    .then((r) => r.data);
}

/** 撤销（paid→revoked）。reason ≥5 字必填。 */
export function revokeOrder(orderNo: string, reason: string): Promise<Order> {
  return http.post<Order>(`/admin/orders/${orderNo}/revoke`, { reason }).then((r) => r.data);
}

export { getErrorMessage };
